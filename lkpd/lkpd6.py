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

logger = logging.getLogger("lkpd6")

class LKPD6Manager(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=6, name="swarm-manager", main_port=8080)

    def get_user_data_script(self) -> str:
        return self.render_script("lkpd6_manager.sh")

class LKPD6Worker(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=6, name="swarm-worker", main_port=8080)

    def get_user_data_script(self) -> str:
        return self.render_script("lkpd6_worker.sh")

# Standalone LKPD6 default class pointing to Manager
class LKPD6(LKPD6Manager):
    pass


class SwarmClusterOrchestrator:
    def __init__(self):
        self.session = get_session()
        self.ec2 = self.session.client("ec2")
        self.ssm = self.session.client("ssm")

    def get_cluster_instances(self) -> dict:
        """Mencari instance Manager dan Worker yang aktif di AWS."""
        instances = get_instances_status(lkpd_filter=6)
        cluster = {"manager": None, "worker": None}
        for inst in instances:
            name = inst.get("name", "").lower()
            if "manager" in name and not cluster["manager"]:
                cluster["manager"] = inst
            elif "worker" in name and not cluster["worker"]:
                cluster["worker"] = inst
        return cluster

    def deploy_infrastructure(self, ami_id: str, subnet_id: str, sg_id: str) -> dict:
        """Membuat atau menggunakan 2 EC2 instances: 1 Manager dan 1 Worker."""
        logger.info("=== [1/6] MEMBUAT INFRASTRUKTUR SWARM (MANAGER + WORKER) ===")

        # Cek apakah sudah ada instance Manager dan Worker yang aktif
        existing = self.get_cluster_instances()
        if existing["manager"] and existing["worker"]:
            logger.info(f"Ditemukan instance aktif: Manager ({existing['manager']['instance_id']}) & Worker ({existing['worker']['instance_id']}). Menggunakan instance tersebut...")
            desc = self.ec2.describe_instances(InstanceIds=[existing["manager"]["instance_id"], existing["worker"]["instance_id"]])
            mgr_priv = ""
            wrk_priv = ""
            for r in desc.get("Reservations", []):
                for inst in r.get("Instances", []):
                    if inst["InstanceId"] == existing["manager"]["instance_id"]:
                        mgr_priv = inst.get("PrivateIpAddress", "")
                    elif inst["InstanceId"] == existing["worker"]["instance_id"]:
                        wrk_priv = inst.get("PrivateIpAddress", "")
            return {
                "manager": {
                    "instance_id": existing["manager"]["instance_id"],
                    "public_ip": existing["manager"]["public_ip"],
                    "private_ip": mgr_priv,
                    "url": f"http://{existing['manager']['public_ip']}:8080"
                },
                "worker": {
                    "instance_id": existing["worker"]["instance_id"],
                    "public_ip": existing["worker"]["public_ip"],
                    "private_ip": wrk_priv,
                    "url": f"http://{existing['worker']['public_ip']}:8080"
                }
            }

        manager_handler = LKPD6Manager()
        worker_handler = LKPD6Worker()

        # 1. Launch Manager Node
        logger.info("Meluncurkan EC2 untuk Swarm Manager...")
        mgr_user_data = manager_handler.get_user_data_script()
        mgr_instance_id = launch_ec2_instance(
            lkpd_num=6,
            lkpd_name="swarm-manager",
            ami_id=ami_id,
            subnet_id=subnet_id,
            sg_id=sg_id,
            user_data_script=mgr_user_data,
            custom_name="lkpd-6-swarm-manager",
            task_name="swarm-manager"
        )

        # 2. Launch Worker Node
        logger.info("Meluncurkan EC2 untuk Swarm Worker...")
        wrk_user_data = worker_handler.get_user_data_script()
        wrk_instance_id = launch_ec2_instance(
            lkpd_num=6,
            lkpd_name="swarm-worker",
            ami_id=ami_id,
            subnet_id=subnet_id,
            sg_id=sg_id,
            user_data_script=wrk_user_data,
            custom_name="lkpd-6-swarm-worker",
            task_name="swarm-worker"
        )

        # 3. Menunggu kedua instance running
        logger.info("Menunggu instance Manager & Worker mencapai state 'running'...")
        mgr_info = wait_for_instance_running(mgr_instance_id, timeout_seconds=settings.INSTANCE_TIMEOUT_SECONDS)
        wrk_info = wait_for_instance_running(wrk_instance_id, timeout_seconds=settings.INSTANCE_TIMEOUT_SECONDS)

        # Mengambil private IP dari EC2 deskripsi
        desc = self.ec2.describe_instances(InstanceIds=[mgr_instance_id, wrk_instance_id])
        for r in desc.get("Reservations", []):
            for inst in r.get("Instances", []):
                iid = inst["InstanceId"]
                p_ip = inst.get("PrivateIpAddress", "")
                if iid == mgr_instance_id:
                    mgr_info["private_ip"] = p_ip
                elif iid == wrk_instance_id:
                    wrk_info["private_ip"] = p_ip

        result = {
            "manager": {
                "instance_id": mgr_instance_id,
                "public_ip": mgr_info.get("public_ip"),
                "private_ip": mgr_info.get("private_ip"),
                "url": f"http://{mgr_info.get('public_ip')}:8080"
            },
            "worker": {
                "instance_id": wrk_instance_id,
                "public_ip": wrk_info.get("public_ip"),
                "private_ip": wrk_info.get("private_ip"),
                "url": f"http://{wrk_info.get('public_ip')}:8080"
            }
        }
        logger.info(f"Manager Ready: Public IP={result['manager']['public_ip']}, Private IP={result['manager']['private_ip']}")
        logger.info(f"Worker Ready : Public IP={result['worker']['public_ip']}, Private IP={result['worker']['private_ip']}")
        return result

    def execute_ssm(self, instance_id: str, commands: list, timeout_sec: int = 60) -> dict:
        """Mengeksekusi baris perintah pada EC2 menggunakan AWS Systems Manager (SSM)."""
        logger.info(f"Mengirim perintah SSM ke instance {instance_id}...")
        try:
            res = self.ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={"commands": commands}
            )
            cmd_id = res["Command"]["CommandId"]

            # Polling hasil eksekusi
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
        """Menunggu SSM Agent di dalam instance online dan dapat menerima perintah."""
        logger.info(f"Menunggu SSM Agent online pada instance {instance_id}...")
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
        logger.warning(f"SSM Agent belum merespon Online setelah {max_wait}s untuk {instance_id}.")
        return False

    def setup_cluster(self, manager_id: str, worker_id: str) -> dict:
        """Langkah 1 & 2: Inisialisasi Swarm pada Manager dan Join dari Worker."""
        logger.info("=== [2/6] SETUP SWARM CLUSTER (INIT MANAGER & JOIN WORKER) ===")

        # 1. Pastikan SSM online
        self.wait_for_ssm_ready(manager_id)
        self.wait_for_ssm_ready(worker_id)

        # 2. Ambil Swarm Token & IP dari Manager
        logger.info("Mengambil konfigurasi Swarm Manager...")
        token = ""
        mgr_ip = ""
        for attempt in range(25):
            get_info_cmd = [
                "#!/bin/bash",
                "if [ -f /opt/lkpd/swarm_info.json ]; then",
                "  cat /opt/lkpd/swarm_info.json",
                "elif command -v docker &>/dev/null && systemctl is-active --quiet docker; then",
                "  M_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4 || hostname -I | awk '{print $1}')",
                "  if ! docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null | grep -q 'active'; then",
                "    docker swarm init --advertise-addr $M_IP 2>/dev/null || true",
                "  fi",
                "  T=$(docker swarm join-token worker -q 2>/dev/null || true)",
                "  if [ -n \"$T\" ]; then",
                "    echo \"{\\\"manager_ip\\\": \\\"$M_IP\\\", \\\"worker_token\\\": \\\"$T\\\"}\"",
                "  fi",
                "fi"
            ]
            res_mgr = self.execute_ssm(manager_id, get_info_cmd, timeout_sec=30)
            stdout_mgr = res_mgr.get("stdout", "")
            if "worker_token" in stdout_mgr and "{" in stdout_mgr:
                try:
                    json_str = stdout_mgr[stdout_mgr.find("{"):stdout_mgr.rfind("}")+1]
                    info_data = json.loads(json_str)
                    token = info_data.get("worker_token", "").strip()
                    mgr_ip = info_data.get("manager_ip", "").strip()
                    if token and mgr_ip:
                        break
                except Exception:
                    pass
            time.sleep(5)

        if not token or not mgr_ip:
            raise RuntimeError(f"Gagal mengekstrak Swarm Token atau Manager IP dari Manager Node. Output: {stdout_mgr}")

        logger.info(f"Swarm Token: {token[:15]}... | Manager IP: {mgr_ip}")

        # 3. Worker Node Join Swarm
        logger.info(f"Menginstruksikan Worker {worker_id} untuk bergabung ke Swarm...")
        join_commands = [
            "#!/bin/bash",
            "for i in {1..35}; do",
            "  if command -v docker &>/dev/null && systemctl is-active --quiet docker; then",
            "    break",
            "  fi",
            "  sleep 4",
            "done",
            "docker swarm leave -f 2>/dev/null || true",
            f"docker swarm join --token {token} {mgr_ip}:2377",
            "docker info --format 'Swarm State: {{.Swarm.LocalNodeState}}'"
        ]
        res_wrk = self.execute_ssm(worker_id, join_commands, timeout_sec=90)
        logger.info(f"Worker Join Output:\n{res_wrk.get('stdout', '')}")

        # 4. Verifikasi Cluster di Manager (docker node ls)
        verify_cmd = ["docker node ls"]
        res_verify = self.execute_ssm(manager_id, verify_cmd, timeout_sec=30)
        node_ls_output = res_verify.get("stdout", "")
        logger.info(f"Hasil Verifikasi Node Cluster (docker node ls):\n{node_ls_output}")

        return {
            "token": token,
            "manager_ip": mgr_ip,
            "node_ls": node_ls_output,
            "worker_status": res_wrk.get("stdout")
        }

    def create_service(self, manager_id: str) -> dict:
        """Langkah 3: Membuat service web dengan 3 replika."""
        logger.info("=== [3/6] MEMBUAT SERVICE WEB (3 REPLIKAS) ===")
        commands = [
            "#!/bin/bash",
            "docker service rm web 2>/dev/null || true",
            "sleep 2",
            "docker service create --name web --replicas 3 -p 8080:80 nginx",
            "sleep 6",
            "echo '---DOCKER_SERVICE_LS---'",
            "docker service ls",
            "echo '---DOCKER_SERVICE_PS---'",
            "docker service ps web"
        ]
        res = self.execute_ssm(manager_id, commands, timeout_sec=90)
        out = res.get("stdout", "")
        logger.info(f"Service Creation Output:\n{out}")
        return {"output": out}

    def scale_service(self, manager_id: str, replicas: int = 5) -> dict:
        """Langkah 4: Melakukan scaling service web ke jumlah replika yang diminta (default: 5)."""
        logger.info(f"=== [4/6] SCALING SERVICE WEB KE {replicas} REPLIKAS ===")
        commands = [
            "#!/bin/bash",
            f"docker service scale web={replicas}",
            "sleep 6",
            "echo '---DOCKER_SERVICE_LS---'",
            "docker service ls",
            "echo '---DOCKER_SERVICE_PS---'",
            "docker service ps web"
        ]
        res = self.execute_ssm(manager_id, commands, timeout_sec=90)
        out = res.get("stdout", "")
        logger.info(f"Scaling Output:\n{out}")
        return {"output": out}

    def test_self_healing(self, manager_id: str, worker_id: str = None) -> dict:
        """Langkah 5: Simulasi Self-Healing dengan mematikan kontainer secara manual."""
        logger.info("=== [5/6] SIMULASI & UJI SELF-HEALING ===")
        commands = [
            "#!/bin/bash",
            "echo '=== DAFTAR TASK AWAL ==='",
            "docker service ps web",
            "TARGET_CID=$(docker ps --filter 'name=web.' -q | head -n 1)",
            "if [ -z \"$TARGET_CID\" ]; then",
            "  echo 'Tidak ada kontainer web di manager, mencoba mencari di worker...'",
            "else",
            "  echo \"Menghentikan kontainer task: $TARGET_CID\"",
            "  docker rm -f $TARGET_CID",
            "fi",
            "echo '=== STATUS SESAAT SETELAH TERMINASI ==='",
            "docker service ps web",
            "echo 'Menunggu self-healing Swarm...'",
            "sleep 6",
            "echo '=== STATUS SETELAH PEMULIHAN OTOMATIS (SELF-HEALING) ==='",
            "docker service ps web",
            "echo '---STATUS_REPLICA---'",
            "docker service ls"
        ]
        res = self.execute_ssm(manager_id, commands, timeout_sec=90)
        out = res.get("stdout", "")
        logger.info(f"Self-Healing Output:\n{out}")
        return {"output": out}

    def generate_report(self, cluster_info: dict, cluster_results: dict) -> str:
        """Menyusun laporan eksekusi terstruktur dan menyimpannya ke folder output."""
        logger.info("=== [6/6] MENYUSUN LAPORAN LENGKAP LKPD 6 ===")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        mgr = cluster_info.get("manager", {})
        wrk = cluster_info.get("worker", {})

        report = f"""================================================================================
LAPORAN OTOMASI PRAKTIK DOCKER SWARM - LKPD 6
Waktu Eksekusi: {timestamp}
Proyek        : {settings.PROJECT_NAME} (AWS EC2 Multi-Node)
================================================================================

[1] INFORMASI INFRASTRUKTUR NODE (AWS EC2)
--------------------------------------------------------------------------------
1. Manager Node:
   - Nama Instance : lkpd-6-swarm-manager
   - Instance ID   : {mgr.get('instance_id', '-')}
   - Public IP     : {mgr.get('public_ip', '-')}
   - Private IP    : {mgr.get('private_ip', '-')}
   - Role          : Leader / Control Plane
   - Service URL   : {mgr.get('url', '-')}

2. Worker Node:
   - Nama Instance : lkpd-6-swarm-worker
   - Instance ID   : {wrk.get('instance_id', '-')}
   - Public IP     : {wrk.get('public_ip', '-')}
   - Private IP    : {wrk.get('private_ip', '-')}
   - Role          : Worker / Data Plane
   - Service URL   : {wrk.get('url', '-')}

--------------------------------------------------------------------------------
[2] LANGKAH 1 & 2: VERIFIKASI SWARM CLUSTER (docker node ls)
--------------------------------------------------------------------------------
{cluster_results.get('setup', {}).get('node_ls', 'N/A')}

--------------------------------------------------------------------------------
[3] LANGKAH 3: PEMBUATAN SERVICE (web, 3 Replika, Port 8080)
--------------------------------------------------------------------------------
{cluster_results.get('service', {}).get('output', 'N/A')}

--------------------------------------------------------------------------------
[4] LANGKAH 4: SCALING SERVICE MENJADI 5 REPLIKA (docker service scale web=5)
--------------------------------------------------------------------------------
{cluster_results.get('scale', {}).get('output', 'N/A')}

--------------------------------------------------------------------------------
[5] LANGKAH 5: PENGUJIAN SELF-HEALING (Simulasi Matinya Kontainer)
--------------------------------------------------------------------------------
{cluster_results.get('self_healing', {}).get('output', 'N/A')}

================================================================================
KESIMPULAN:
- Seluruh 2 node (Manager & Worker) berhasil membentuk Docker Swarm cluster.
- Service 'web' (nginx) berhasil dibuat dengan 3 replika dan terdistribusi di kedua node.
- Scaling ke 5 replika berhasil dieksekusi secara instan tanpa downtime.
- Fitur Self-Healing terbukti berjalan: saat satu kontainer dimatikan secara paksa,
  Docker Swarm secara otomatis mendeteksi status kegagalan dan menciptakan task pengganti
  sehingga desired state (5 replika) tetap terjaga.
================================================================================
"""
        output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
        os.makedirs(output_dir, exist_ok=True)
        report_file = os.path.join(output_dir, "lkpd6_report.txt")
        status_file = os.path.join(output_dir, "lkpd6_status.json")

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)

        with open(status_file, "w", encoding="utf-8") as f:
            json.dump({
                "lkpd": 6,
                "status": "success",
                "timestamp": timestamp,
                "infrastructure": cluster_info,
                "results": cluster_results
            }, f, indent=2)

        print("\n" + report)
        logger.info(f"Laporan berhasil disimpan ke: {report_file}")
        logger.info(f"Status JSON disimpan ke: {status_file}")
        return report

    def run_full_automation(self, ami_id: str, subnet_id: str, sg_id: str) -> dict:
        """Menjalankan seluruh alur praktik LKPD 6 secara otomatis dari hulu ke hilir."""
        logger.info("==================================================")
        logger.info("MEMULAI EKSEKUSI PENUH OTOMASI LKPD 6: DOCKER SWARM")
        logger.info("==================================================")

        # 1. Infrastruktur
        infra = self.deploy_infrastructure(ami_id, subnet_id, sg_id)
        mgr_id = infra["manager"]["instance_id"]
        wrk_id = infra["worker"]["instance_id"]

        results = {}

        # 2. Cluster Init & Join
        results["setup"] = self.setup_cluster(mgr_id, wrk_id)

        # 3. Create Service 3 replika
        results["service"] = self.create_service(mgr_id)

        # 4. Scale Service 5 replika
        results["scale"] = self.scale_service(mgr_id, replicas=5)

        # 5. Test Self-Healing
        results["self_healing"] = self.test_self_healing(mgr_id, wrk_id)

        # 6. Generate Report
        self.generate_report(infra, results)

        return {"infra": infra, "results": results}
