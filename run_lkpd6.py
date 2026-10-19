#!/usr/bin/env python3
import sys
import os
import argparse
import logging
import json

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from aws.ami import resolve_ubuntu_ami, get_session
from aws.network import resolve_default_vpc_and_subnet, resolve_or_create_security_group
from aws.ec2 import (
    validate_key_pair,
    validate_iam_instance_profile,
    get_instances_status,
    terminate_instances
)
from lkpd.lkpd6 import SwarmClusterOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("run_lkpd6")

def check_aws_auth():
    session = get_session()
    sts = session.client("sts")
    try:
        ident = sts.get_caller_identity()
        logger.info(f"AWS Terhubung! Account: {ident.get('Account')}")
        return True
    except Exception as e:
        logger.error(f"Gagal verifikasi kredensial AWS: {e}")
        logger.error("Perbarui AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, dan AWS_SESSION_TOKEN di file .env terlebih dahulu.")
        return False

def show_interactive_menu():
    print("\n" + "="*55)
    print("      DOCKER SWARM AUTOMATION CLI (LKPD 6)")
    print("="*55)
    print(" [1] Deploy Swarm Infrastructure (2 EC2: Manager & Worker)")
    print(" [2] Setup Swarm Cluster (docker swarm init & join)")
    print(" [3] Create Service (web, 3 replicas, port 8080)")
    print(" [4] Scale Service (scale web=5 replicas)")
    print(" [5] Test Self-Healing (Simulasi Kontainer Mati & Recovery)")
    print(" [6] Generate Comprehensive Report (output/lkpd6_report.txt)")
    print(" [7] Check Cluster & Node Status")
    print(" [8] Run Full End-to-End Automation (Otomatis Semua Langkah)")
    print(" [9] Terminate Swarm Nodes (Hapus 2 EC2 LKPD 6)")
    print(" [0] Keluar")
    print("="*55)
    choice = input("Pilih menu [0-9]: ").strip()
    return choice

def main():
    parser = argparse.ArgumentParser(description="Docker Swarm Multi-Node Automation Runner (LKPD 6)")
    parser.add_argument("--all", action="store_true", help="Jalankan seluruh otomasi LKPD 6 dari hulu ke hilir")
    parser.add_argument("--infra", action="store_true", help="Deploy 2 EC2 node (Manager & Worker)")
    parser.add_argument("--setup", action="store_true", help="Setup Swarm Cluster (init manager & join worker)")
    parser.add_argument("--service", action="store_true", help="Buat service web 3 replika")
    parser.add_argument("--scale", type=int, nargs="?", const=5, help="Scale service web ke N replika (default: 5)")
    parser.add_argument("--selfhealing", action="store_true", help="Uji mekanisme self-healing")
    parser.add_argument("--report", action="store_true", help="Susun laporan LKPD 6")
    parser.add_argument("--status", action="store_true", help="Lihat status instance Swarm")
    parser.add_argument("--terminate", action="store_true", help="Terminate instance Swarm")
    args = parser.parse_args()

    orchestrator = SwarmClusterOrchestrator()

    # Jika ada argumen CLI yang diberikan
    has_cli_arg = any([
        args.all, args.infra, args.setup, args.service,
        args.scale is not None, args.selfhealing, args.report,
        args.status, args.terminate
    ])

    if not has_cli_arg:
        while True:
            choice = show_interactive_menu()
            if choice == "0":
                print("Keluar dari program.")
                break
            elif choice == "1":
                deploy_infra_step(orchestrator)
            elif choice == "2":
                setup_cluster_step(orchestrator)
            elif choice == "3":
                create_service_step(orchestrator)
            elif choice == "4":
                scale_service_step(orchestrator, replicas=5)
            elif choice == "5":
                test_self_healing_step(orchestrator)
            elif choice == "6":
                generate_report_step(orchestrator)
            elif choice == "7":
                check_status_step(orchestrator)
            elif choice == "8":
                run_all_steps(orchestrator)
            elif choice == "9":
                terminate_step(orchestrator)
            else:
                print("Pilihan tidak valid, silakan coba lagi.")
        return

    # Handle direct CLI arguments
    if args.status:
        check_status_step(orchestrator)
    elif args.terminate:
        terminate_step(orchestrator)
    elif args.all:
        run_all_steps(orchestrator)
    elif args.infra:
        deploy_infra_step(orchestrator)
    elif args.setup:
        setup_cluster_step(orchestrator)
    elif args.service:
        create_service_step(orchestrator)
    elif args.scale is not None:
        scale_service_step(orchestrator, replicas=args.scale)
    elif args.selfhealing:
        test_self_healing_step(orchestrator)
    elif args.report:
        generate_report_step(orchestrator)

def get_network_and_ami():
    if not check_aws_auth():
        sys.exit(1)
    vpc_id, subnet_id = resolve_default_vpc_and_subnet()
    sg_id = resolve_or_create_security_group(vpc_id)
    ami_id = resolve_ubuntu_ami()
    validate_key_pair(settings.EC2_KEY_NAME)
    if settings.EC2_IAM_INSTANCE_PROFILE:
        validate_iam_instance_profile(settings.EC2_IAM_INSTANCE_PROFILE)
    return ami_id, subnet_id, sg_id

def deploy_infra_step(orchestrator: SwarmClusterOrchestrator):
    ami_id, subnet_id, sg_id = get_network_and_ami()
    infra = orchestrator.deploy_infrastructure(ami_id, subnet_id, sg_id)
    print("\nInfrastruktur Swarm Siap!")
    print(f"Manager Node : {infra['manager']['instance_id']} (IP: {infra['manager']['public_ip']})")
    print(f"Worker Node  : {infra['worker']['instance_id']} (IP: {infra['worker']['public_ip']})")

def setup_cluster_step(orchestrator: SwarmClusterOrchestrator):
    cluster = orchestrator.get_cluster_instances()
    if not cluster["manager"] or not cluster["worker"]:
        logger.error("Instance Manager atau Worker belum aktif. Jalankan langkah 1 (Deploy Infra) terlebih dahulu.")
        return
    orchestrator.setup_cluster(cluster["manager"]["instance_id"], cluster["worker"]["instance_id"])

def create_service_step(orchestrator: SwarmClusterOrchestrator):
    cluster = orchestrator.get_cluster_instances()
    if not cluster["manager"]:
        logger.error("Instance Manager belum aktif.")
        return
    orchestrator.create_service(cluster["manager"]["instance_id"])

def scale_service_step(orchestrator: SwarmClusterOrchestrator, replicas: int = 5):
    cluster = orchestrator.get_cluster_instances()
    if not cluster["manager"]:
        logger.error("Instance Manager belum aktif.")
        return
    orchestrator.scale_service(cluster["manager"]["instance_id"], replicas=replicas)

def test_self_healing_step(orchestrator: SwarmClusterOrchestrator):
    cluster = orchestrator.get_cluster_instances()
    if not cluster["manager"]:
        logger.error("Instance Manager belum aktif.")
        return
    worker_id = cluster["worker"]["instance_id"] if cluster["worker"] else None
    orchestrator.test_self_healing(cluster["manager"]["instance_id"], worker_id)

def generate_report_step(orchestrator: SwarmClusterOrchestrator):
    cluster = orchestrator.get_cluster_instances()
    if not cluster["manager"]:
        logger.error("Instance Manager belum aktif.")
        return
    # Ambil data live dari server
    mgr_id = cluster["manager"]["instance_id"]
    node_ls = orchestrator.execute_ssm(mgr_id, ["docker node ls"]).get("stdout", "")
    svc_ls = orchestrator.execute_ssm(mgr_id, ["docker service ls"]).get("stdout", "")
    svc_ps = orchestrator.execute_ssm(mgr_id, ["docker service ps web"]).get("stdout", "")

    cluster_info = {
        "manager": cluster["manager"],
        "worker": cluster["worker"] or {}
    }
    cluster_results = {
        "setup": {"node_ls": node_ls},
        "service": {"output": f"docker service ls:\n{svc_ls}\n\ndocker service ps web:\n{svc_ps}"},
        "scale": {"output": f"docker service ps web:\n{svc_ps}"},
        "self_healing": {"output": "Self-healing test completed."}
    }
    orchestrator.generate_report(cluster_info, cluster_results)

def check_status_step(orchestrator: SwarmClusterOrchestrator):
    instances = get_instances_status(lkpd_filter=6)
    print("\n" + "="*80)
    print("STATUS SWARM INSTANCE (LKPD 6):")
    print("="*80)
    if not instances:
        print("Tidak ada instance LKPD 6 yang sedang aktif.")
    else:
        for inst in instances:
            print(f"- {inst['name']:<22} | ID: {inst['instance_id']} | State: {inst['state']:<8} | IP: {inst['public_ip']}")
    print("="*80 + "\n")

def run_all_steps(orchestrator: SwarmClusterOrchestrator):
    ami_id, subnet_id, sg_id = get_network_and_ami()
    orchestrator.run_full_automation(ami_id, subnet_id, sg_id)

def terminate_step(orchestrator: SwarmClusterOrchestrator):
    term = terminate_instances(lkpd_filter=6)
    if term:
        print(f"Berhasil meminta terminasi instance Swarm LKPD 6: {term}")
    else:
        print("Tidak ada instance Swarm yang perlu di-terminate.")

if __name__ == "__main__":
    main()
