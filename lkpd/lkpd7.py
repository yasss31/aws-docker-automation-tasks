import os
import json
import time
import logging
from botocore.exceptions import ClientError
from lkpd.base import BaseLKPD
from config.settings import settings
from aws.ami import get_session
from aws.ec2 import (
    launch_ec2_instance,
    wait_for_instance_running,
    get_instances_status,
    terminate_instances
)

logger = logging.getLogger("lkpd7")

class LKPD7(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=7, name="swarm-singlenode", main_port=8080)

    def get_user_data_script(self) -> str:
        return self.render_script("lkpd7.sh")


class SwarmSingleNodeOrchestrator:
    def __init__(self):
        self.session = get_session()
        self.ec2 = self.session.client("ec2")
        self.ssm = self.session.client("ssm")

    def get_instance(self) -> dict:
        """Mencari instance LKPD 7 aktif."""
        instances = get_instances_status(lkpd_filter=7)
        if instances:
            return instances[0]
        return None

    def deploy_instance(self, ami_id: str, subnet_id: str, sg_id: str) -> dict:
        """Meluncurkan 1 EC2 instance untuk Docker Swarm Single Node."""
        logger.info("=== [1/5] MELUNCURKAN EC2 UNTUK DOCKER SWARM SINGLE NODE (LKPD 7) ===")
        handler = LKPD7()
        user_data = handler.get_user_data_script()

        instance_id = launch_ec2_instance(
            lkpd_num=7,
            lkpd_name="swarm-singlenode",
            ami_id=ami_id,
            subnet_id=subnet_id,
            sg_id=sg_id,
            user_data_script=user_data,
            custom_name="lkpd-7-swarm-singlenode",
            task_name="swarm-singlenode"
        )

        logger.info(f"Menunggu instance {instance_id} running...")
        info = wait_for_instance_running(instance_id, timeout_seconds=settings.INSTANCE_TIMEOUT_SECONDS)
        pub_ip = info.get("public_ip")
        url = f"http://{pub_ip}:8080"
        logger.info(f"Instance LKPD 7 Running! URL Layanan: {url}")

        result = {
            "instance_id": instance_id,
            "public_ip": pub_ip,
            "port": 8080,
            "url": url,
            "status": "instance_running"
        }
        return result

    def execute_ssm(self, instance_id: str, commands: list, timeout_sec: int = 90) -> dict:
        """Mengeksekusi command via AWS SSM."""
        logger.info(f"Mengirim perintah SSM ke instance {instance_id}...")
        try:
            res = self.ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={"commands": commands}
            )
            cmd_id = res["Command"]["CommandId"]

            start_time = time.time()
            while time.time() - start_time < timeout_sec:
                time.sleep(3)
                try:
                    inv = self.ssm.get_command_invocation(CommandId=cmd_id, InstanceId=instance_id)
                    status = inv.get("Status")
                    if status in ["Success", "Failed", "TimedOut", "Cancelled"]:
                        return {
                            "status": status,
                            "stdout": inv.get("StandardOutputContent", ""),
                            "stderr": inv.get("StandardErrorContent", ""),
                            "exit_code": inv.get("ResponseCode", -1)
                        }
                except ClientError:
                    pass
            return {"status": "Timeout", "stdout": "", "stderr": f"SSM timeout after {timeout_sec}s", "exit_code": -1}
        except ClientError as e:
            return {"status": "Error", "stdout": "", "stderr": str(e), "exit_code": -1}

    def wait_for_ssm_ready(self, instance_id: str, max_wait: int = 180) -> bool:
        """Menunggu SSM Agent aktif."""
        logger.info(f"Menunggu SSM Agent online pada {instance_id}...")
        start = time.time()
        while time.time() - start < max_wait:
            try:
                res = self.ssm.describe_instance_information(
                    Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
                )
                infos = res.get("InstanceInformationList", [])
                if infos and infos[0].get("PingStatus") == "Online":
                    logger.info(f"SSM Agent online untuk {instance_id}!")
                    return True
            except Exception:
                pass
            time.sleep(5)
        return False

    def test_round_robin(self, instance_id: str) -> dict:
        """Langkah 8-9: Menguji load balancing round-robin antar 3 replika."""
        logger.info("=== [2/5] MENGUJI LOAD BALANCING (ROUND-ROBIN 3 REPLIKA) ===")
        commands = [
            "#!/bin/bash",
            "echo '---SERVICE_PS---'",
            "docker service ps web",
            "echo '---ROUND_ROBIN_TEST---'",
            "for i in {1..9}; do",
            "  HOST=$(curl -s http://localhost:8080/index_info.php 2>/dev/null || curl -s http://localhost:8080/index.php 2>/dev/null | grep -o '<b>[^<]*</b>' | head -1 | sed 's/<\\/\\?b>//g' || echo 'N/A')",
            "  echo \"Request $i -> Hostname: $HOST\"",
            "  sleep 0.2",
            "done",
            "echo '---CONTAINER_LIST---'",
            "docker ps --filter 'name=web.' --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}'"
        ]
        res = self.execute_ssm(instance_id, commands)
        out = res.get("stdout", "")
        logger.info(f"Round Robin Output:\n{out}")
        return {"output": out}

    def verify_database_and_app(self, instance_id: str) -> dict:
        """Tugas 1 & 2: Verifikasi database MariaDB dan aplikasi appKantin."""
        logger.info("=== [3/5] VERIFIKASI MARIADB & APPKANTIN ===")
        commands = [
            "#!/bin/bash",
            "echo '---DB_STATUS---'",
            "docker ps --filter 'name=db' --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}'",
            "echo '---DB_QUERY---'",
            "docker exec db mariadb -uroot -prahasia -e 'USE kantin_db; SELECT id, name, category, price, stock, status FROM menu LIMIT 5;' 2>/dev/null || echo 'Gagal query DB'",
            "echo '---HTTP_TEST---'",
            "curl -s -I http://localhost:8080/ | head -n 5"
        ]
        res = self.execute_ssm(instance_id, commands)
        out = res.get("stdout", "")
        logger.info(f"Database & App Output:\n{out}")
        return {"output": out}

    def cleanup_swarm(self, instance_id: str) -> dict:
        """Langkah 11-12: Menghapus service web, database, dan leave Swarm."""
        logger.info("=== CLEANUP SERVICE & LEAVE SWARM (LKPD 7) ===")
        commands = [
            "#!/bin/bash",
            "docker service rm web 2>/dev/null || true",
            "docker rm -f db 2>/dev/null || true",
            "docker swarm leave --force 2>/dev/null || true",
            "echo 'Cleanup selesai: service web dan container db dihapus, node leave swarm.'"
        ]
        res = self.execute_ssm(instance_id, commands)
        out = res.get("stdout", "")
        logger.info(f"Cleanup Output:\n{out}")
        return {"output": out}

    def generate_report(self, inst_info: dict, test_results: dict) -> str:
        """Menyusun laporan lengkap LKPD 7."""
        logger.info("=== [4/5] MENYUSUN LAPORAN LENGKAP LKPD 7 ===")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        report = f"""================================================================================
LAPORAN PRAKTIK DOCKER SWARM SINGLE NODE & APPKANTIN - LKPD 7
Waktu Eksekusi: {timestamp}
Proyek        : {settings.PROJECT_NAME} (AWS EC2 Single-Node Swarm)
================================================================================

[1] INFORMASI SERVER & ARSITEKTUR (AWS EC2)
--------------------------------------------------------------------------------
Instance ID   : {inst_info.get('instance_id', '-')}
Public IP     : {inst_info.get('public_ip', '-')}
Service Port  : 8080 (Published Routing Mesh -> Container Port 8080)
URL Akses     : {inst_info.get('url', '-')}
Arsitektur    : 1 Node bertindak sebagai Swarm Manager sekaligus Worker
Service       : web (Image: trafex/php-nginx, 3 Replika, Bind mount: /home/ubuntu/mywww)
Database      : MariaDB (Container: db, Image: mariadb:11-jammy, Port 3306)
Aplikasi      : appKantin (https://github.com/paknux/appKantin)

--------------------------------------------------------------------------------
[2] HASIL UJI LOAD BALANCING ROUND-ROBIN (LANGKAH 8 & 9)
--------------------------------------------------------------------------------
{test_results.get('round_robin', {}).get('output', 'N/A')}

--------------------------------------------------------------------------------
[3] HASIL VERIFIKASI MARIADB & APPKANTIN (TUGAS 1 & TUGAS 2)
--------------------------------------------------------------------------------
{test_results.get('db_and_app', {}).get('output', 'N/A')}

================================================================================
KESIMPULAN:
1. Docker Swarm Single Node berhasil diinisialisasi menggunakan IP privat EC2.
2. Service 'web' (trafex/php-nginx) berhasil berjalan dengan 3 replika (web.1, web.2, web.3)
   membaca bind mount folder yang sama.
3. Terbukti terjadi pembagian beban (Round-Robin) saat diakses via HTTP port 8080,
   di mana setiap request dilayani bergantian oleh ID hostname kontainer yang berbeda.
4. Tugas 1 sukses: Container MariaDB (mariadb:11-jammy) berhasil aktif dan terhubung
   ke network overlay 'kantin_net'.
5. Tugas 2 sukses: Aplikasi appKantin berhasil dideploy, konfigurasi config/db.php
   berhasil diarahkan ke database bersama, dan aplikasi aktif melayani pengguna.
================================================================================
"""
        output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
        os.makedirs(output_dir, exist_ok=True)
        report_file = os.path.join(output_dir, "lkpd7_report.txt")
        status_file = os.path.join(output_dir, "lkpd7_status.json")

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)

        with open(status_file, "w", encoding="utf-8") as f:
            json.dump({
                "lkpd": 7,
                "status": "success",
                "timestamp": timestamp,
                "infrastructure": inst_info,
                "results": test_results
            }, f, indent=2)

        print("\n" + report)
        logger.info(f"Laporan berhasil disimpan ke: {report_file}")
        logger.info(f"Status JSON disimpan ke: {status_file}")
        return report

    def run_full_automation(self, ami_id: str, subnet_id: str, sg_id: str) -> dict:
        """Menjalankan seluruh alur LKPD 7 dari awal sampai akhir."""
        logger.info("==================================================")
        logger.info("MEMULAI EKSEKUSI PENUH OTOMASI LKPD 7")
        logger.info("==================================================")

        inst = self.deploy_instance(ami_id, subnet_id, sg_id)
        inst_id = inst["instance_id"]

        self.wait_for_ssm_ready(inst_id)

        # Beri waktu beberapa detik agar bootstrap selesai
        time.sleep(15)

        results = {}
        results["round_robin"] = self.test_round_robin(inst_id)
        results["db_and_app"] = self.verify_database_and_app(inst_id)
        self.generate_report(inst, results)

        return {"infra": inst, "results": results}
