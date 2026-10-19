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
from lkpd.lkpd7 import SwarmSingleNodeOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("run_lkpd7")

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
    print("\n" + "="*60)
    print("     DOCKER SWARM SINGLE NODE & APPKANTIN (LKPD 7)")
    print("="*60)
    print(" [1] Deploy Swarm Infrastructure (1 EC2 Single Node)")
    print(" [2] Setup Web Service (trafex/php-nginx, Scale 3 Replika)")
    print(" [3] Test Load Balancing (Round-Robin 9x Request)")
    print(" [4] Deploy MariaDB Database (Tugas 1)")
    print(" [5] Deploy appKantin & Konfigurasi db.php (Tugas 2)")
    print(" [6] Verifikasi Penuh & Susun Laporan")
    print(" [7] Cleanup Swarm Service (docker service rm & leave)")
    print(" [8] Run Full End-to-End Automation (Otomatis Semua Langkah)")
    print(" [9] Terminate EC2 Instance LKPD 7")
    print(" [0] Keluar")
    print("="*60)
    choice = input("Pilih menu [0-9]: ").strip()
    return choice

def main():
    parser = argparse.ArgumentParser(description="Docker Swarm Single Node & appKantin Automation Runner (LKPD 7)")
    parser.add_argument("--all", action="store_true", help="Jalankan seluruh otomasi LKPD 7 dari hulu ke hilir")
    parser.add_argument("--infra", action="store_true", help="Deploy 1 EC2 node Swarm Single Node")
    parser.add_argument("--web", action="store_true", help="Setup service web 3 replika")
    parser.add_argument("--test-rr", action="store_true", help="Uji load balancing round-robin antar replika")
    parser.add_argument("--db", action="store_true", help="Deploy container MariaDB (Tugas 1)")
    parser.add_argument("--kantin", action="store_true", help="Deploy dan konfigurasi appKantin (Tugas 2)")
    parser.add_argument("--verify", action="store_true", help="Verifikasi seluruh status aplikasi dan database")
    parser.add_argument("--cleanup", action="store_true", help="Hapus service web dan keluar dari swarm")
    parser.add_argument("--status", action="store_true", help="Lihat status instance LKPD 7")
    parser.add_argument("--terminate", action="store_true", help="Terminate instance LKPD 7")
    args = parser.parse_args()

    orchestrator = SwarmSingleNodeOrchestrator()

    has_cli_arg = any([
        args.all, args.infra, args.web, args.test_rr, args.db,
        args.kantin, args.verify, args.cleanup, args.status, args.terminate
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
                setup_web_step(orchestrator)
            elif choice == "3":
                test_rr_step(orchestrator)
            elif choice == "4":
                setup_db_step(orchestrator)
            elif choice == "5":
                deploy_kantin_step(orchestrator)
            elif choice == "6":
                verify_and_report_step(orchestrator)
            elif choice == "7":
                cleanup_step(orchestrator)
            elif choice == "8":
                run_all_steps(orchestrator)
            elif choice == "9":
                terminate_step(orchestrator)
            else:
                print("Pilihan tidak valid, silakan coba lagi.")
        return

    # Direct CLI argument handling
    if args.status:
        check_status_step()
    elif args.terminate:
        terminate_step(orchestrator)
    elif args.all:
        run_all_steps(orchestrator)
    elif args.infra:
        deploy_infra_step(orchestrator)
    elif args.web:
        setup_web_step(orchestrator)
    elif args.test_rr:
        test_rr_step(orchestrator)
    elif args.db:
        setup_db_step(orchestrator)
    elif args.kantin:
        deploy_kantin_step(orchestrator)
    elif args.verify:
        verify_and_report_step(orchestrator)
    elif args.cleanup:
        cleanup_step(orchestrator)

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

def deploy_infra_step(orchestrator: SwarmSingleNodeOrchestrator):
    ami_id, subnet_id, sg_id = get_network_and_ami()
    inst = orchestrator.deploy_instance(ami_id, subnet_id, sg_id)
    print("\nInfrastruktur LKPD 7 Siap!")
    print(f"Instance ID : {inst['instance_id']}")
    print(f"Public IP   : {inst['public_ip']}")
    print(f"URL Akses   : {inst['url']}")

def setup_web_step(orchestrator: SwarmSingleNodeOrchestrator):
    inst = orchestrator.get_instance()
    if not inst:
        logger.error("Instance LKPD 7 belum aktif. Jalankan langkah 1 terlebih dahulu.")
        return
    iid = inst["instance_id"]
    with open(os.path.join(os.path.dirname(__file__), "scripts", "lkpd7", "02_setup_web_service.sh"), "r", encoding="utf-8") as f:
        cmd_content = f.read()
    res = orchestrator.execute_ssm(iid, [cmd_content])
    print(res.get("stdout", ""))

def test_rr_step(orchestrator: SwarmSingleNodeOrchestrator):
    inst = orchestrator.get_instance()
    if not inst:
        logger.error("Instance LKPD 7 belum aktif.")
        return
    res = orchestrator.test_round_robin(inst["instance_id"])
    print(res.get("output", ""))

def setup_db_step(orchestrator: SwarmSingleNodeOrchestrator):
    inst = orchestrator.get_instance()
    if not inst:
        logger.error("Instance LKPD 7 belum aktif.")
        return
    with open(os.path.join(os.path.dirname(__file__), "scripts", "lkpd7", "04_setup_mariadb.sh"), "r", encoding="utf-8") as f:
        cmd_content = f.read()
    res = orchestrator.execute_ssm(inst["instance_id"], [cmd_content])
    print(res.get("stdout", ""))

def deploy_kantin_step(orchestrator: SwarmSingleNodeOrchestrator):
    inst = orchestrator.get_instance()
    if not inst:
        logger.error("Instance LKPD 7 belum aktif.")
        return
    with open(os.path.join(os.path.dirname(__file__), "scripts", "lkpd7", "05_deploy_appkantin.sh"), "r", encoding="utf-8") as f:
        cmd_content = f.read()
    res = orchestrator.execute_ssm(inst["instance_id"], [cmd_content])
    print(res.get("stdout", ""))

def verify_and_report_step(orchestrator: SwarmSingleNodeOrchestrator):
    inst = orchestrator.get_instance()
    if not inst:
        logger.error("Instance LKPD 7 belum aktif.")
        return
    iid = inst["instance_id"]
    rr_res = orchestrator.test_round_robin(iid)
    db_res = orchestrator.verify_database_and_app(iid)
    results = {"round_robin": rr_res, "db_and_app": db_res}
    orchestrator.generate_report(inst, results)

def cleanup_step(orchestrator: SwarmSingleNodeOrchestrator):
    inst = orchestrator.get_instance()
    if not inst:
        logger.error("Instance LKPD 7 belum aktif.")
        return
    res = orchestrator.cleanup_swarm(inst["instance_id"])
    print(res.get("output", ""))

def check_status_step():
    instances = get_instances_status(lkpd_filter=7)
    print("\n" + "="*80)
    print("STATUS SWARM SINGLE NODE INSTANCE (LKPD 7):")
    print("="*80)
    if not instances:
        print("Tidak ada instance LKPD 7 yang sedang aktif.")
    else:
        for inst in instances:
            print(f"- {inst['name']:<25} | ID: {inst['instance_id']} | State: {inst['state']:<8} | IP: {inst['public_ip']}")
    print("="*80 + "\n")

def run_all_steps(orchestrator: SwarmSingleNodeOrchestrator):
    ami_id, subnet_id, sg_id = get_network_and_ami()
    orchestrator.run_full_automation(ami_id, subnet_id, sg_id)

def terminate_step(orchestrator: SwarmSingleNodeOrchestrator):
    term = terminate_instances(lkpd_filter=7)
    if term:
        print(f"Berhasil meminta terminasi instance LKPD 7: {term}")
    else:
        print("Tidak ada instance LKPD 7 yang perlu di-terminate.")

if __name__ == "__main__":
    main()
