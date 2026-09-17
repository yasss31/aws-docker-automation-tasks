import argparse
import sys
import os
import json
import logging
import time

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from aws.ami import resolve_ubuntu_ami, get_session
from aws.network import resolve_default_vpc_and_subnet, resolve_or_create_security_group
from aws.diagnostics import inspect_all
from aws.ec2 import (
    validate_key_pair,
    validate_iam_instance_profile,
    launch_ec2_instance,
    wait_for_instance_running,
    get_instances_status,
    terminate_instances
)
from lkpd.lkpd1 import LKPD1
from lkpd.lkpd2 import LKPD2
from lkpd.lkpd3 import LKPD3
from lkpd.lkpd4 import LKPD4
from lkpd.lkpd5 import LKPD5
from lkpd.tugas2 import Tugas2
from lkpd.tugas3 import Tugas3

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("main")

LKPD_MAP = {
    1: LKPD1,
    2: LKPD2,
    3: LKPD3,
    4: LKPD4,
    5: LKPD5
}

def cmd_validate(args):
    logger.info("=== PRE-FLIGHT VALIDATION CHECK ===")
    errors = []

    # 1. AWS Credentials
    session = get_session()
    sts = session.client("sts")
    try:
        caller = sts.get_caller_identity()
        logger.info(f"AWS Credential Terhubung! Account: {caller.get('Account')}, Arn: {caller.get('Arn')}")
    except Exception as e:
        errors.append(f"Gagal verifikasi kredensial AWS: {e}")

    # 2. Region & Default VPC/Subnet
    vpc_id = None
    try:
        vpc_id, subnet_id = resolve_default_vpc_and_subnet()
        logger.info(f"VPC Valid: {vpc_id}, Subnet: {subnet_id}")
    except Exception as e:
        errors.append(f"Gagal resolve VPC/Subnet: {e}")

    # 3. AMI
    try:
        ami_id = resolve_ubuntu_ami()
        logger.info(f"AMI Valid: {ami_id}")
    except Exception as e:
        errors.append(f"Gagal resolve AMI: {e}")

    # 4. Key Pair
    try:
        validate_key_pair(settings.EC2_KEY_NAME)
    except Exception as e:
        errors.append(str(e))

    # 5. IAM Instance Profile
    if settings.EC2_IAM_INSTANCE_PROFILE:
        try:
            validate_iam_instance_profile(settings.EC2_IAM_INSTANCE_PROFILE)
        except Exception as e:
            errors.append(str(e))

    # 6. Security Group
    if vpc_id:
        try:
            sg_id = resolve_or_create_security_group(vpc_id)
            logger.info(f"Security Group Siap: {sg_id}")
        except Exception as e:
            errors.append(f"Security Group error: {e}")

    # 7. LKPD 4 Docker Hub credentials warning
    if not settings.DOCKERHUB_USERNAME or not settings.DOCKERHUB_TOKEN:
        logger.warning("Catatan: Kredensial Docker Hub belum diisi di .env. LKPD 4 akan berjalan dalam mode LOCAL/PARTIAL.")

    print("\n" + "="*50)
    if errors:
        logger.error(f"Ditemukan {len(errors)} kendala pra-eksekusi:")
        for idx, err in enumerate(errors, 1):
            print(f"  {idx}. {err}")
        sys.exit(1)
    else:
        logger.info("SEMUA VALIDASI BERHASIL! Lingkungan AWS siap menjalankan otomasi LKPD.")
        print("="*50 + "\n")

def deploy_single_lkpd(lkpd_num: int, ami_id: str, subnet_id: str, sg_id: str) -> dict:
    handler_class = LKPD_MAP.get(lkpd_num)
    if not handler_class:
        raise ValueError(f"Nomor LKPD tidak dikenal: {lkpd_num}")

    handler = handler_class()
    logger.info(f"--- MENYIAPKAN LKPD {lkpd_num}: {handler.name.upper()} ---")

    user_data = handler.get_user_data_script()
    instance_id = launch_ec2_instance(
        lkpd_num=lkpd_num,
        lkpd_name=handler.name,
        ami_id=ami_id,
        subnet_id=subnet_id,
        sg_id=sg_id,
        user_data_script=user_data
    )

    info = wait_for_instance_running(instance_id, timeout_seconds=settings.INSTANCE_TIMEOUT_SECONDS)
    pub_ip = info.get("public_ip")
    url = f"http://{pub_ip}:{handler.main_port}"
    logger.info(f"Instance LKPD {lkpd_num} Running! URL Layanan: {url}")

    result = {
        "lkpd": lkpd_num,
        "name": handler.name,
        "instance_id": instance_id,
        "public_ip": pub_ip,
        "port": handler.main_port,
        "url": url,
        "status": "instance_running"
    }
    return result

def deploy_tugas2(ami_id: str, subnet_id: str, sg_id: str) -> dict:
    handler = Tugas2()
    logger.info("--- MENYIAPKAN TUGAS 2: APP ID CARD (DOCKER COMPOSE) ---")

    user_data = handler.get_user_data_script()
    instance_id = launch_ec2_instance(
        lkpd_num=handler.lkpd_num,
        lkpd_name=handler.name,
        ami_id=ami_id,
        subnet_id=subnet_id,
        sg_id=sg_id,
        user_data_script=user_data,
        custom_name="tugas-2-idcard",
        task_name="tugas2"
    )

    info = wait_for_instance_running(instance_id, timeout_seconds=settings.INSTANCE_TIMEOUT_SECONDS)
    pub_ip = info.get("public_ip")
    url = f"http://{pub_ip}:{handler.main_port}"
    logger.info(f"Instance Tugas 2 Running! URL Layanan: {url}")

    result = {
        "lkpd": "tugas2",
        "name": "tugas-2-idcard",
        "instance_id": instance_id,
        "public_ip": pub_ip,
        "port": handler.main_port,
        "url": url,
        "status": "instance_running"
    }
    return result

def deploy_tugas3(ami_id: str, subnet_id: str, sg_id: str) -> dict:
    handler = Tugas3()
    logger.info("--- MENYIAPKAN TUGAS 3: APP RESERVASI RUANGAN (DOCKER COMPOSE) ---")

    user_data = handler.get_user_data_script()
    instance_id = launch_ec2_instance(
        lkpd_num=handler.lkpd_num,
        lkpd_name=handler.name,
        ami_id=ami_id,
        subnet_id=subnet_id,
        sg_id=sg_id,
        user_data_script=user_data,
        custom_name="tugas-3-reservasi",
        task_name="tugas3"
    )

    info = wait_for_instance_running(instance_id, timeout_seconds=settings.INSTANCE_TIMEOUT_SECONDS)
    pub_ip = info.get("public_ip")
    url = f"http://{pub_ip}:{handler.main_port}"
    logger.info(f"Instance Tugas 3 Running! URL Layanan: {url}")

    result = {
        "lkpd": "tugas3",
        "name": "tugas-3-reservasi",
        "instance_id": instance_id,
        "public_ip": pub_ip,
        "port": handler.main_port,
        "url": url,
        "status": "instance_running"
    }
    return result

def cmd_create(args):
    logger.info("Menyiapkan resource jaringan dan AMI dasar...")
    vpc_id, subnet_id = resolve_default_vpc_and_subnet()
    sg_id = resolve_or_create_security_group(vpc_id)
    ami_id = resolve_ubuntu_ami()

    validate_key_pair(settings.EC2_KEY_NAME)
    if settings.EC2_IAM_INSTANCE_PROFILE:
        validate_iam_instance_profile(settings.EC2_IAM_INSTANCE_PROFILE)

    results = []
    if getattr(args, "tugas3", False):
        logger.info("Memulai pembuatan instance khusus Tugas 3 (App Reservasi Ruangan)...")
        res = deploy_tugas3(ami_id, subnet_id, sg_id)
        results.append(res)
    elif getattr(args, "tugas2", False):
        logger.info("Memulai pembuatan instance khusus Tugas 2 (App ID Card)...")
        res = deploy_tugas2(ami_id, subnet_id, sg_id)
        results.append(res)
    elif args.all:
        logger.info("Memulai pembuatan seluruh 5 LKPD secara berurutan...")
        for num in range(1, 6):
            res = deploy_single_lkpd(num, ami_id, subnet_id, sg_id)
            results.append(res)
            time.sleep(2)
    elif args.lkpd:
        res = deploy_single_lkpd(args.lkpd, ami_id, subnet_id, sg_id)
        results.append(res)
    else:
        logger.error("Tentukan opsi --lkpd <1-5>, --tugas2, --tugas3, atau --all.")
        sys.exit(1)

    summary_file = os.path.join(os.path.dirname(__file__), "output", "summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "="*70)
    print("RINGKASAN HASIL DEPLOYMENT EC2:")
    print("="*70)
    for r in results:
        if r['lkpd'] == 'tugas2':
            task_title = f"Tugas 2 ({r['name']})"
        elif r['lkpd'] == 'tugas3':
            task_title = f"Tugas 3 ({r['name']})"
        else:
            task_title = f"LKPD {r['lkpd']} ({r['name']})"
        print(f"{task_title}:")
        print(f"  Instance ID : {r['instance_id']}")
        print(f"  Public IP   : {r['public_ip']}")
        print(f"  URL Akses   : {r['url']}")
        print("-"*70)
    print(f"Data disimpan ke: {summary_file}\n")


def cmd_status(args):
    task_filter = None
    if getattr(args, "tugas3", False):
        task_filter = "tugas3"
    elif getattr(args, "tugas2", False):
        task_filter = "tugas2"
    instances = get_instances_status(lkpd_filter=args.lkpd, task_filter=task_filter)
    print("\n" + "="*85)
    print(f"STATUS INSTANCE AWS ({len(instances)} ditemukan):")
    print("="*85)
    if not instances:
        print("Tidak ada instance yang sedang aktif.")
    else:
        header = f"{'TASK/LKPD':<10} | {'NAMA':<22} | {'INSTANCE ID':<20} | {'STATE':<10} | {'PUBLIC IP':<15}"
        print(header)
        print("-" * len(header))
        for i in instances:
            task_type = i.get("task", "lkpd")
            if task_type == "tugas3" or "tugas-3" in i['name'].lower():
                display_tag = "Tugas 3"
            elif task_type == "tugas2" or "tugas" in i['name'].lower():
                display_tag = "Tugas 2"
            else:
                display_tag = f"LKPD {i['lkpd']}"
            print(f"{display_tag:<10} | {i['name']:<22} | {i['instance_id']:<20} | {i['state']:<10} | {i['public_ip']:<15}")
    print("="*85 + "\n")

def cmd_inspect(args):
    inspect_all()

def cmd_terminate(args):
    is_tugas2 = getattr(args, "tugas2", False)
    is_tugas3 = getattr(args, "tugas3", False)
    if not args.all and not args.lkpd and not is_tugas2 and not is_tugas3:
        logger.error("Gunakan flag --lkpd <1-5>, --tugas2, --tugas3, atau --all untuk terminate.")
        sys.exit(1)

    task_filter = "tugas3" if is_tugas3 else ("tugas2" if is_tugas2 else None)
    lkpd_filter = args.lkpd if not args.all and not is_tugas2 and not is_tugas3 else None
    term_ids = terminate_instances(lkpd_filter=lkpd_filter, task_filter=task_filter)
    if term_ids:
        logger.info(f"Berhasil meminta terminasi untuk {len(term_ids)} instance: {term_ids}")
    else:
        logger.info("Tidak ada instance yang di-terminate.")

def main():
    parser = argparse.ArgumentParser(description="AWS LKPD Docker Automation CLI (Boto3 + UserData)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Validate
    sub_val = subparsers.add_parser("validate", help="Pre-flight check seluruh konfigurasi AWS & kredensial")
    sub_val.set_defaults(func=cmd_validate)

    # Create
    sub_create = subparsers.add_parser("create", help="Membuat EC2 dan menjalankan otomatisasi LKPD / Tugas 2 / Tugas 3")
    group_create = sub_create.add_mutually_exclusive_group(required=True)
    group_create.add_argument("--lkpd", type=int, choices=[1, 2, 3, 4, 5], help="Nomor LKPD tertentu (1-5)")
    group_create.add_argument("--all", action="store_true", help="Deploy seluruh LKPD (1 sampai 5)")
    group_create.add_argument("--tugas2", action="store_true", help="Deploy instance baru khusus Tugas 2 (App ID Card)")
    group_create.add_argument("--tugas3", action="store_true", help="Deploy instance baru khusus Tugas 3 (App Reservasi Ruangan)")
    sub_create.set_defaults(func=cmd_create)

    # Status
    sub_status = subparsers.add_parser("status", help="Melihat status instance aktif")
    group_status = sub_status.add_mutually_exclusive_group(required=False)
    group_status.add_argument("--lkpd", type=int, choices=[1, 2, 3, 4, 5], help="Filter berdasarkan nomor LKPD")
    group_status.add_argument("--tugas2", action="store_true", help="Filter khusus instance Tugas 2")
    group_status.add_argument("--tugas3", action="store_true", help="Filter khusus instance Tugas 3")
    sub_status.set_defaults(func=cmd_status)

    # Inspect (Diagnosa Dalam Server)
    sub_insp = subparsers.add_parser("inspect", help="Diagnosa mendalam runtime server (HTTP, status.json, kontainer docker)")
    sub_insp.set_defaults(func=cmd_inspect)

    # Terminate
    sub_term = subparsers.add_parser("terminate", help="Menghentikan / menghapus instance")
    group_term = sub_term.add_mutually_exclusive_group(required=True)
    group_term.add_argument("--lkpd", type=int, choices=[1, 2, 3, 4, 5], help="Nomor LKPD yang ingin di-terminate")
    group_term.add_argument("--all", action="store_true", help="Terminate semua instance LKPD")
    group_term.add_argument("--tugas2", action="store_true", help="Terminate khusus instance Tugas 2")
    group_term.add_argument("--tugas3", action="store_true", help="Terminate khusus instance Tugas 3")
    sub_term.set_defaults(func=cmd_terminate)


    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
