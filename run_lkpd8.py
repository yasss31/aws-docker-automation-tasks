#!/usr/bin/env python3
import sys
import os
import argparse
import logging
import json
import time

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from aws.ami import resolve_ubuntu_ami, get_session
from aws.network import resolve_default_vpc_and_subnet
from aws.ec2 import (
    validate_key_pair,
    validate_iam_instance_profile,
    get_instances_status,
    terminate_instances
)
from lkpd.lkpd8 import Swarm3NodeClusterOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("run_lkpd8")

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
    print("\n" + "="*65)
    print("      DOCKER SWARM 3 NODE & MARIADB MULTI-INSTANCE (LKPD 8)")
    print("="*65)
    print(" [1] Deploy Infrastruktur AWS (4 EC2: manager, worker1, worker2, db)")
    print(" [2] Inisialisasi Cluster Swarm (Join worker1 & worker2 ke manager)")
    print(" [3] Setup Service Web 3 Replika (trafex/php-nginx port 8080)")
    print(" [4] Uji Routing Mesh & Round-Robin (6x Request port 8080)")
    print(" [5] Uji Ketahanan Klaster (Scale up/down, Rolling Update, Drain node)")
    print(" [6] Deploy MariaDB 11.8 di Instance DB & Test Koneksi (Tugas 1 & 2)")
    print(" [7] Deploy appKantin 3 Replika & Konfigurasi db.php (Tugas 3, 4, 5)")
    print(" [8] Deploy Docker Stack kantin-stack.yml (Tugas 6 - Tantangan)")
    print(" [9] Verifikasi Penuh Seluruh Komponen & Database Query")
    print(" [10] Cleanup Swarm Services (docker service rm & stack rm)")
    print(" [11] Run Full End-to-End Automation (Eksekusi Lengkap Seluruh Tahapan)")
    print(" [12] Terminate 4 Instance EC2 LKPD 8")
    print(" [0] Keluar")
    print("="*65)
    choice = input("Pilih menu [0-12]: ").strip()
    return choice

def ensure_cluster_ready(orchestrator):
    cluster = orchestrator.get_cluster_instances()
    if not all(cluster.values()):
        logger.info("Infrastruktur belum lengkap. Menyiapkan 4 EC2 instances...")
        vpc_id, subnet_id = resolve_default_vpc_and_subnet()
        ami_id = resolve_ubuntu_ami()
        sg_id = orchestrator.resolve_or_create_sg_swarm(vpc_id)
        cluster = orchestrator.deploy_infrastructure(ami_id, subnet_id, sg_id)
    return cluster

def main():
    parser = argparse.ArgumentParser(description="Docker Swarm 3 Node Cluster & MariaDB Runner (LKPD 8)")
    parser.add_argument("--all", action="store_true", help="Jalankan seluruh otomasi LKPD 8 dari hulu ke hilir")
    parser.add_argument("--infra", action="store_true", help="Deploy 4 EC2 instances dan Security Group swarm-sg")
    parser.add_argument("--swarm-init", dest="swarm_init", action="store_true", help="Inisialisasi Swarm dan hubungkan kedua worker")
    parser.add_argument("--web", action="store_true", help="Deploy service web 3 replika trafex/php-nginx")
    parser.add_argument("--test-rr", action="store_true", help="Uji routing mesh round-robin 6x request")
    parser.add_argument("--resilience", action="store_true", help="Uji skalabilitas, rolling update, dan drain worker2")
    parser.add_argument("--db", action="store_true", help="Deploy MariaDB 11.8 di instance db")
    parser.add_argument("--kantin", action="store_true", help="Deploy appKantin 3 replika dengan DB terpusat")
    parser.add_argument("--stack", action="store_true", help="Deploy tantangan Docker Stack kantin-stack.yml")
    parser.add_argument("--verify", action="store_true", help="Verifikasi komprehensif cluster dan database")
    parser.add_argument("--cleanup", action="store_true", help="Hapus services dan stacks di cluster")
    parser.add_argument("--terminate", action="store_true", help="Hentikan dan terminate 4 instance LKPD 8")
    parser.add_argument("--status", action="store_true", help="Lihat status 4 instance LKPD 8")
    args = parser.parse_args()

    orchestrator = Swarm3NodeClusterOrchestrator()

    if not check_aws_auth():
        sys.exit(1)

    has_cli = any([
        args.all, args.infra, args.swarm_init, args.web, args.test_rr,
        args.resilience, args.db, args.kantin, args.stack, args.verify,
        args.cleanup, args.terminate, args.status
    ])

    if not has_cli:
        while True:
            choice = show_interactive_menu()
            if choice == "0":
                print("Keluar dari program.")
                break
            elif choice == "1":
                vpc_id, subnet_id = resolve_default_vpc_and_subnet()
                ami_id = resolve_ubuntu_ami()
                sg_id = orchestrator.resolve_or_create_sg_swarm(vpc_id)
                cluster = orchestrator.deploy_infrastructure(ami_id, subnet_id, sg_id)
                print("Infrastruktur 4 EC2 siap.")
            elif choice == "2":
                cluster = ensure_cluster_ready(orchestrator)
                orchestrator.init_swarm_cluster(cluster)
            elif choice == "3":
                cluster = ensure_cluster_ready(orchestrator)
                orchestrator.setup_web_service(cluster)
            elif choice == "4":
                cluster = ensure_cluster_ready(orchestrator)
                orchestrator.test_routing_mesh(cluster)
            elif choice == "5":
                cluster = ensure_cluster_ready(orchestrator)
                orchestrator.test_resilience_and_drain(cluster)
            elif choice == "6":
                cluster = ensure_cluster_ready(orchestrator)
                orchestrator.setup_mariadb_database(cluster)
            elif choice == "7":
                cluster = ensure_cluster_ready(orchestrator)
                orchestrator.deploy_appkantin(cluster)
            elif choice == "8":
                cluster = ensure_cluster_ready(orchestrator)
                orchestrator.deploy_stack_tantangan(cluster)
            elif choice == "9":
                cluster = ensure_cluster_ready(orchestrator)
                orchestrator.verify_all(cluster)
            elif choice == "10":
                cluster = ensure_cluster_ready(orchestrator)
                orchestrator.cleanup(cluster)
            elif choice == "11":
                print("\nMenjalankan Full End-to-End Automation LKPD 8...")
                vpc_id, subnet_id = resolve_default_vpc_and_subnet()
                ami_id = resolve_ubuntu_ami()
                sg_id = orchestrator.resolve_or_create_sg_swarm(vpc_id)
                cluster = orchestrator.deploy_infrastructure(ami_id, subnet_id, sg_id)
                orchestrator.init_swarm_cluster(cluster)
                orchestrator.setup_web_service(cluster)
                orchestrator.test_routing_mesh(cluster)
                orchestrator.test_resilience_and_drain(cluster)
                orchestrator.setup_mariadb_database(cluster)
                orchestrator.deploy_appkantin(cluster)
                orchestrator.deploy_stack_tantangan(cluster)
                orchestrator.verify_all(cluster)
                print("\nSelamat! Seluruh tahapan LKPD 8 berhasil diselesaikan secara otomatis!")
            elif choice == "12":
                cluster = orchestrator.get_cluster_instances()
                confirm = input("Apakah Anda yakin ingin men-terminate ke-4 instance EC2? (y/N): ").strip().lower()
                if confirm == "y":
                    orchestrator.terminate_cluster(cluster)
                    print("Terminasi 4 instance berhasil dikirim.")
            else:
                print("Pilihan tidak valid, silakan coba lagi.")
    else:
        # CLI execution
        if args.status:
            cluster = orchestrator.get_cluster_instances()
            print(json.dumps(cluster, indent=2))
        elif args.infra:
            vpc_id, subnet_id = resolve_default_vpc_and_subnet()
            ami_id = resolve_ubuntu_ami()
            sg_id = orchestrator.resolve_or_create_sg_swarm(vpc_id)
            orchestrator.deploy_infrastructure(ami_id, subnet_id, sg_id)
        elif getattr(args, "swarm_init", False):
            cluster = ensure_cluster_ready(orchestrator)
            orchestrator.init_swarm_cluster(cluster)
        elif args.web:
            cluster = ensure_cluster_ready(orchestrator)
            orchestrator.setup_web_service(cluster)
        elif args.test_rr:
            cluster = ensure_cluster_ready(orchestrator)
            orchestrator.test_routing_mesh(cluster)
        elif args.resilience:
            cluster = ensure_cluster_ready(orchestrator)
            orchestrator.test_resilience_and_drain(cluster)
        elif args.db:
            cluster = ensure_cluster_ready(orchestrator)
            orchestrator.setup_mariadb_database(cluster)
        elif args.kantin:
            cluster = ensure_cluster_ready(orchestrator)
            orchestrator.deploy_appkantin(cluster)
        elif args.stack:
            cluster = ensure_cluster_ready(orchestrator)
            orchestrator.deploy_stack_tantangan(cluster)
        elif args.verify:
            cluster = ensure_cluster_ready(orchestrator)
            orchestrator.verify_all(cluster)
        elif args.cleanup:
            cluster = ensure_cluster_ready(orchestrator)
            orchestrator.cleanup(cluster)
        elif args.terminate:
            cluster = orchestrator.get_cluster_instances()
            orchestrator.terminate_cluster(cluster)
        elif args.all:
            vpc_id, subnet_id = resolve_default_vpc_and_subnet()
            ami_id = resolve_ubuntu_ami()
            sg_id = orchestrator.resolve_or_create_sg_swarm(vpc_id)
            cluster = orchestrator.deploy_infrastructure(ami_id, subnet_id, sg_id)
            orchestrator.init_swarm_cluster(cluster)
            orchestrator.setup_web_service(cluster)
            orchestrator.test_routing_mesh(cluster)
            orchestrator.test_resilience_and_drain(cluster)
            orchestrator.setup_mariadb_database(cluster)
            orchestrator.deploy_appkantin(cluster)
            orchestrator.deploy_stack_tantangan(cluster)
            orchestrator.verify_all(cluster)
            print("\nEksekusi Penuh LKPD 8 Selesai.")

if __name__ == "__main__":
    main()
