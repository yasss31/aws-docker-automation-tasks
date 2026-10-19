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

logger = logging.getLogger("lkpd8")

class LKPD8Manager(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=8, name="swarm-manager", main_port=8080)

    def get_user_data_script(self) -> str:
        return self.render_script("lkpd8_manager.sh")

class LKPD8Worker1(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=8, name="swarm-worker1", main_port=8080)

    def get_user_data_script(self) -> str:
        return self.render_script("lkpd8_worker.sh", extra_env={"WORKER_NAME": "worker1"})

class LKPD8Worker2(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=8, name="swarm-worker2", main_port=8080)

    def get_user_data_script(self) -> str:
        return self.render_script("lkpd8_worker.sh", extra_env={"WORKER_NAME": "worker2"})

class LKPD8Database(BaseLKPD):
    def __init__(self):
        super().__init__(lkpd_num=8, name="swarm-db", main_port=3306)

    def get_user_data_script(self) -> str:
        return self.render_script("lkpd8_db.sh")

# Standalone LKPD8 default alias
class LKPD8(LKPD8Manager):
    pass


class Swarm3NodeClusterOrchestrator:
    def __init__(self):
        self.session = get_session()
        self.ec2 = self.session.client("ec2")
        self.ssm = self.session.client("ssm")

    def resolve_or_create_sg_swarm(self, vpc_id: str) -> str:
        """
        Membuat atau mencari Security Group 'swarm-sg' sesuai spesifikasi LKPD 8 Halaman 3:
        (Nama disesuaikan menjadi 'swarm-sg' karena AWS melarang GroupName diawali prefix 'sg-*')
        - 22: TCP 0.0.0.0/0 (Akses SSH)
        - 2377: TCP swarm-sg (Komunikasi manajemen cluster)
        - 7946: TCP & UDP swarm-sg (Discovery antar node)
        - 4789: UDP swarm-sg (Overlay network VXLAN)
        - 8080: TCP 0.0.0.0/0 (Akses web browser)
        - 3306: TCP swarm-sg (Akses database dari node swarm)
        """
        sg_name = "swarm-sg"
        logger.info(f"Mencari atau membuat Security Group {sg_name} pada VPC {vpc_id}...")
        sg_id = None
        try:
            res = self.ec2.describe_security_groups(Filters=[
                {"Name": "group-name", "Values": [sg_name]},
                {"Name": "vpc-id", "Values": [vpc_id]}
            ])
            sgs = res.get("SecurityGroups", [])
            if sgs:
                sg_id = sgs[0]["GroupId"]
                logger.info(f"Security Group {sg_name} ditemukan: {sg_id}")
        except ClientError as e:
            logger.warning(f"Error checking {sg_name}: {e}")

        if not sg_id:
            logger.info(f"Membuat Security Group {sg_name} baru...")
            try:
                res = self.ec2.create_security_group(
                    GroupName=sg_name,
                    Description="Security Group khusus LKPD 8 Docker Swarm 3 Node Cluster & MariaDB",
                    VpcId=vpc_id,
                    TagSpecifications=[{
                        "ResourceType": "security-group",
                        "Tags": [
                            {"Key": "Name", "Value": sg_name},
                            {"Key": "Project", "Value": settings.PROJECT_NAME},
                            {"Key": "LKPD", "Value": "8"}
                        ]
                    }]
                )
                sg_id = res["GroupId"]
                logger.info(f"Security Group {sg_name} berhasil dibuat: {sg_id}")
            except ClientError as e:
                raise RuntimeError(f"Gagal membuat {sg_name}: {e}")

        # Sinkronisasi Inbound Rules LKPD 8
        try:
            res = self.ec2.describe_security_groups(GroupIds=[sg_id])
            existing_perms = res["SecurityGroups"][0].get("IpPermissions", [])

            # Kumpulkan existing rules
            existing_cidr = set()
            existing_groups = set()
            for p in existing_perms:
                proto = p.get("IpProtocol", "")
                from_p = p.get("FromPort", 0)
                for r in p.get("IpRanges", []):
                    existing_cidr.add((proto, from_p, r.get("CidrIp")))
                for g in p.get("UserIdGroupPairs", []):
                    existing_groups.add((proto, from_p, g.get("GroupId")))

            rules_to_authorize = []

            # Rule CIDR 0.0.0.0/0
            for port in [22, 8080]:
                if ("tcp", port, "0.0.0.0/0") not in existing_cidr:
                    rules_to_authorize.append({
                        "IpProtocol": "tcp",
                        "FromPort": port,
                        "ToPort": port,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": f"Akses port {port} publik"}]
                    })

            # Rule Self-Referencing swarm-sg
            self_rules = [
                ("tcp", 2377, "Swarm Cluster Management"),
                ("tcp", 7946, "Node Discovery Gossip TCP"),
                ("udp", 7946, "Node Discovery Gossip UDP"),
                ("udp", 4789, "Overlay Network VXLAN UDP"),
                ("tcp", 3306, "Akses MariaDB dari Swarm Node")
            ]
            for proto, port, desc in self_rules:
                if (proto, port, sg_id) not in existing_groups:
                    rules_to_authorize.append({
                        "IpProtocol": proto,
                        "FromPort": port,
                        "ToPort": port,
                        "UserIdGroupPairs": [{"GroupId": sg_id, "Description": desc}]
                    })

            if rules_to_authorize:
                logger.info(f"Menambahkan {len(rules_to_authorize)} inbound rules ke {sg_id}...")
                self.ec2.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpPermissions=rules_to_authorize
                )
                logger.info("Inbound rules swarm-sg berhasil disinkronisasi.")
        except ClientError as e:
            logger.warning(f"Catatan sinkronisasi rule SG: {e}")

        return sg_id

    def get_cluster_instances(self) -> dict:
        """Mencari instance cluster LKPD 8 (manager, worker1, worker2, db)."""
        cluster = {"manager": None, "worker1": None, "worker2": None, "db": None}

        # Cari instance berdasarkan tag LKPD 8 langsung via describe_instances
        desc = self.ec2.describe_instances(Filters=[
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopped"]},
            {"Name": "tag:LKPD", "Values": ["8"]}
        ])
        for r in desc.get("Reservations", []):
            for i in r.get("Instances", []):
                t_name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "").lower()
                inst_data = {
                    "instance_id": i["InstanceId"],
                    "public_ip": i.get("PublicIpAddress", "N/A"),
                    "private_ip": i.get("PrivateIpAddress", "N/A"),
                    "state": i["State"]["Name"],
                    "name": t_name
                }
                if "manager" in t_name and not cluster["manager"]:
                    cluster["manager"] = inst_data
                elif "worker1" in t_name and not cluster["worker1"]:
                    cluster["worker1"] = inst_data
                elif "worker2" in t_name and not cluster["worker2"]:
                    cluster["worker2"] = inst_data
                elif ("db" in t_name or "database" in t_name) and not cluster["db"]:
                    cluster["db"] = inst_data

        return cluster

    def deploy_infrastructure(self, ami_id: str, subnet_id: str, sg_id: str) -> dict:
        """Meluncurkan 4 EC2 instances: manager, worker1, worker2, dan db."""
        logger.info("=== [1/7] MENYIAPKAN 4 EC2 INSTANCES UNTUK LKPD 8 ===")
        existing = self.get_cluster_instances()
        if all(existing.values()):
            logger.info("Seluruh 4 instance LKPD 8 sudah ada dan siap digunakan!")
            all_ids = [v["instance_id"] for v in existing.values() if v]
            desc = self.ec2.describe_instances(InstanceIds=all_ids)
            for r in desc.get("Reservations", []):
                for inst in r.get("Instances", []):
                    iid = inst["InstanceId"]
                    for k, v in existing.items():
                        if v and v.get("instance_id") == iid:
                            v["private_ip"] = inst.get("PrivateIpAddress", "N/A")
                            v["public_ip"] = inst.get("PublicIpAddress", "N/A")
            return existing

        mgr_handler = LKPD8Manager()
        w1_handler = LKPD8Worker1()
        w2_handler = LKPD8Worker2()
        db_handler = LKPD8Database()

        # 1. Manager Node
        if not existing["manager"]:
            logger.info("Meluncurkan node 'manager'...")
            mid = launch_ec2_instance(
                lkpd_num=8,
                lkpd_name="swarm-manager",
                ami_id=ami_id,
                subnet_id=subnet_id,
                sg_id=sg_id,
                user_data_script=mgr_handler.get_user_data_script(),
                custom_name="manager",
                task_name="swarm-manager"
            )
            minfo = wait_for_instance_running(mid, timeout_seconds=settings.INSTANCE_TIMEOUT_SECONDS)
            existing["manager"] = {"instance_id": mid, "public_ip": minfo["public_ip"]}

        # 2. Worker 1 Node
        if not existing["worker1"]:
            logger.info("Meluncurkan node 'worker1'...")
            w1id = launch_ec2_instance(
                lkpd_num=8,
                lkpd_name="swarm-worker1",
                ami_id=ami_id,
                subnet_id=subnet_id,
                sg_id=sg_id,
                user_data_script=w1_handler.get_user_data_script(),
                custom_name="worker1",
                task_name="swarm-worker1"
            )
            w1info = wait_for_instance_running(w1id, timeout_seconds=settings.INSTANCE_TIMEOUT_SECONDS)
            existing["worker1"] = {"instance_id": w1id, "public_ip": w1info["public_ip"]}

        # 3. Worker 2 Node
        if not existing["worker2"]:
            logger.info("Meluncurkan node 'worker2'...")
            w2id = launch_ec2_instance(
                lkpd_num=8,
                lkpd_name="swarm-worker2",
                ami_id=ami_id,
                subnet_id=subnet_id,
                sg_id=sg_id,
                user_data_script=w2_handler.get_user_data_script(),
                custom_name="worker2",
                task_name="swarm-worker2"
            )
            w2info = wait_for_instance_running(w2id, timeout_seconds=settings.INSTANCE_TIMEOUT_SECONDS)
            existing["worker2"] = {"instance_id": w2id, "public_ip": w2info["public_ip"]}

        # 4. Database Node
        if not existing["db"]:
            logger.info("Meluncurkan node 'db'...")
            dbid = launch_ec2_instance(
                lkpd_num=8,
                lkpd_name="swarm-db",
                ami_id=ami_id,
                subnet_id=subnet_id,
                sg_id=sg_id,
                user_data_script=db_handler.get_user_data_script(),
                custom_name="db",
                task_name="swarm-db"
            )
            dbinfo = wait_for_instance_running(dbid, timeout_seconds=settings.INSTANCE_TIMEOUT_SECONDS)
            existing["db"] = {"instance_id": dbid, "public_ip": dbinfo["public_ip"]}

        # Refresh private IPs
        all_ids = [v["instance_id"] for v in existing.values() if v]
        desc = self.ec2.describe_instances(InstanceIds=all_ids)
        for r in desc.get("Reservations", []):
            for inst in r.get("Instances", []):
                iid = inst["InstanceId"]
                for k, v in existing.items():
                    if v and v.get("instance_id") == iid:
                        v["private_ip"] = inst.get("PrivateIpAddress", "")
                        v["public_ip"] = inst.get("PublicIpAddress", "")

        logger.info("=== 4 INSTANCE LKPD 8 BERHASIL DISIAPKAN ===")
        for k, v in existing.items():
            logger.info(f"Node [{k.upper()}]: ID={v['instance_id']}, PubIP={v.get('public_ip')}, PrivIP={v.get('private_ip')}")

        return existing

    def execute_ssm(self, instance_id: str, commands: list, timeout_sec: int = 120) -> dict:
        """Mengeksekusi command via AWS SSM."""
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

    def init_swarm_cluster(self, cluster: dict) -> dict:
        """Menginisialisasi Docker Swarm di Manager dan menggabungkan Worker1 & Worker2."""
        logger.info("=== [2/7] MENGHUBUNGKAN CLUSTER SWARM 3 NODE ===")
        mgr_id = cluster["manager"]["instance_id"]
        mgr_priv_ip = cluster["manager"]["private_ip"]

        # 1. Swarm Init di Manager
        init_cmd = [
            f"docker swarm init --advertise-addr {mgr_priv_ip} || true",
            "docker swarm join-token worker -q"
        ]
        res = self.execute_ssm(mgr_id, init_cmd)
        token = res["stdout"].strip().splitlines()[-1] if res["stdout"] else ""
        if not token:
            raise RuntimeError(f"Gagal mengambil token join worker dari manager: {res['stderr']}")
        logger.info("Join Token worker berhasil diperoleh dari manager (tersimpan aman).")

        # 2. Join Worker 1
        w1_id = cluster["worker1"]["instance_id"]
        logger.info(f"Menghubungkan worker1 ({w1_id}) ke Swarm Manager...")
        self.execute_ssm(w1_id, [
            "docker swarm leave 2>/dev/null || true",
            f"docker swarm join --token {token} {mgr_priv_ip}:2377"
        ])

        # 3. Join Worker 2
        w2_id = cluster["worker2"]["instance_id"]
        logger.info(f"Menghubungkan worker2 ({w2_id}) ke Swarm Manager...")
        self.execute_ssm(w2_id, [
            "docker swarm leave 2>/dev/null || true",
            f"docker swarm join --token {token} {mgr_priv_ip}:2377"
        ])

        # 4. Verifikasi docker node ls di Manager
        time.sleep(3)
        node_res = self.execute_ssm(mgr_id, ["docker node ls"])
        logger.info("Status Node Cluster:\n" + node_res["stdout"])
        return {"token": token, "node_ls": node_res["stdout"]}

    def setup_web_service(self, cluster: dict) -> dict:
        """Menyiapkan index.php di seluruh node swarm, membuat service web dan scale ke 3 replika."""
        logger.info("=== [3/7] MENYIAPKAN SERVICE WEB 3 REPLIKA (LANGKAH 4, 5, 6) ===")

        # 1. Siapkan /home/ubuntu/mywww/index.php di ketiga swarm node
        setup_mywww = [
            "mkdir -p /home/ubuntu/mywww",
            """cat << 'EOF' > /home/ubuntu/mywww/index.php
<?php
$hostname = gethostname();
$ip = gethostbyname($hostname);
?>
<!DOCTYPE html>
<html>
<head><title>Info Server</title></head>
<body style="font-family: sans-serif;">
<h2>Info Server</h2>
<p>Hostname: <b><?= htmlspecialchars($hostname) ?></b></p>
<p>IP server: <b><?= htmlspecialchars($ip) ?></b></p>
<p>IP client: <b><?= htmlspecialchars($_SERVER['REMOTE_ADDR']) ?></b></p>
</body>
</html>
EOF""",
            "chmod -R 777 /home/ubuntu/mywww"
        ]

        for role in ["manager", "worker1", "worker2"]:
            inst_id = cluster[role]["instance_id"]
            self.execute_ssm(inst_id, setup_mywww)

        # 2. Deploy service web di manager
        mgr_id = cluster["manager"]["instance_id"]
        deploy_cmds = [
            "docker service rm web 2>/dev/null || true",
            "sleep 2",
            "docker service create --name web -p 8080:8080 --mount type=bind,source=/home/ubuntu/mywww,target=/var/www/html trafex/php-nginx",
            "sleep 3",
            "docker service scale web=3",
            "sleep 5",
            "docker service ps web"
        ]
        res = self.execute_ssm(mgr_id, deploy_cmds)
        logger.info("Hasil Deploy & Scale Service Web:\n" + res["stdout"])
        return {"output": res["stdout"]}

    def test_routing_mesh(self, cluster: dict) -> list:
        """Menguji round-robin load balancing lewat routing mesh (Langkah 7)."""
        logger.info("=== [4/7] UJI ROUTING MESH ROUND-ROBIN (LANGKAH 7) ===")
        mgr_id = cluster["manager"]["instance_id"]
        w1_priv = cluster["worker1"]["private_ip"]

        curl_cmd = [
            f"for i in {{1..6}}; do curl -s -m 3 http://{w1_priv}:8080/index.php | grep -o '<b>[^<]*</b>' | head -1; sleep 0.2; done"
        ]
        res = self.execute_ssm(mgr_id, curl_cmd)
        outputs = [line.strip().replace("<b>", "").replace("</b>", "") for line in res["stdout"].splitlines() if line.strip()]
        logger.info(f"Hasil Uji Round-Robin 6x: {outputs}")
        return outputs

    def test_resilience_and_drain(self, cluster: dict) -> dict:
        """Menguji skalabilitas, rolling update, crash recovery, dan drain node (Langkah 8, 9, 10)."""
        logger.info("=== [5/7] UJI KETAHANAN KLASTER & DRAIN NODE (LANGKAH 8, 9, 10) ===")
        mgr_id = cluster["manager"]["instance_id"]

        cmds = [
            # Langkah 8: Scale up & down
            "docker service scale web=6",
            "sleep 3",
            "docker service scale web=3",
            "sleep 3",
            # Langkah 9: Rolling update
            "docker service update --force --update-parallelism 1 --update-delay 10s web",
            "sleep 5",
            # Langkah 10b: Drain worker2
            "docker node update --availability drain worker2",
            "sleep 3",
            "docker service ps web",
            # Re-activate worker2
            "docker node update --availability active worker2",
            "sleep 2",
            "docker service update --force web",
            "sleep 4",
            "docker service ps web"
        ]
        res = self.execute_ssm(mgr_id, cmds)
        logger.info("Hasil Uji Ketahanan & Drain:\n" + res["stdout"])
        return {"output": res["stdout"]}

    def setup_mariadb_database(self, cluster: dict) -> dict:
        """Menyiapkan MariaDB 11.8 di instance 'db' dan menguji koneksinya dari manager (Tugas 1 & 2)."""
        logger.info("=== [6/7] SETUP MARIADB 11.8 DI INSTANCE DB (TUGAS 1 & 2) ===")
        db_id = cluster["db"]["instance_id"]
        db_priv = cluster["db"]["private_ip"]
        mgr_id = cluster["manager"]["instance_id"]

        # 1. Jalankan MariaDB di instance db
        db_cmds = [
            "docker rm -f db 2>/dev/null || true",
            "docker run -d --name db --restart unless-stopped -p 3306:3306 -e MARIADB_ROOT_PASSWORD=rahasia -v dbdata:/var/lib/mysql mariadb:11.8",
            "sleep 5",
            "docker ps"
        ]
        db_res = self.execute_ssm(db_id, db_cmds)
        logger.info("Status Container MariaDB di DB Node:\n" + db_res["stdout"])

        # 2. Uji koneksi dari Swarm Manager
        time.sleep(3)
        test_cmds = [
            f"docker run --rm -e MYSQL_PWD=rahasia mariadb:11.8 mariadb -h {db_priv} -uroot -e 'SELECT VERSION();'"
        ]
        mgr_res = self.execute_ssm(mgr_id, test_cmds)
        logger.info("Hasil Pengujian Koneksi DB dari Manager:\n" + mgr_res["stdout"])
        return {"db_output": db_res["stdout"], "test_output": mgr_res["stdout"]}

    def deploy_appkantin(self, cluster: dict) -> dict:
        """Deploy appKantin 3 replika dengan database MariaDB terpusat (Tugas 3, 4, 5)."""
        logger.info("=== [7/7] DEPLOY APPKANTIN 3 REPLIKA DI KLASTER SWARM (TUGAS 3 & 4) ===")
        db_priv = cluster["db"]["private_ip"]
        mgr_id = cluster["manager"]["instance_id"]

        kantin_setup = [
            "rm -rf /home/ubuntu/appKantin",
            "git clone https://github.com/paknux/appKantin.git /home/ubuntu/appKantin",
            f"sed -i 's/\\$DB_HOST = \"localhost\";/\\$DB_HOST = \"{db_priv}\";/' /home/ubuntu/appKantin/config/db.php",
            "sed -i 's/\\$DB_PASS = \"\";/\\$DB_PASS = \"rahasia\";/' /home/ubuntu/appKantin/config/db.php",
            "chmod -R 777 /home/ubuntu/appKantin"
        ]

        # Sync ke seluruh 3 swarm node
        for role in ["manager", "worker1", "worker2"]:
            self.execute_ssm(cluster[role]["instance_id"], kantin_setup)

        # Deploy service kantin di manager
        deploy_cmds = [
            "docker service rm web 2>/dev/null || true",
            "docker service rm kantin 2>/dev/null || true",
            "sleep 3",
            "docker service create --name kantin --replicas 3 -p 8080:8080 --mount type=bind,source=/home/ubuntu/appKantin,target=/var/www/html trafex/php-nginx",
            "sleep 6",
            "docker service ps kantin"
        ]
        res = self.execute_ssm(mgr_id, deploy_cmds)
        logger.info("Status Service Kantin:\n" + res["stdout"])
        return {"output": res["stdout"]}

    def deploy_stack_tantangan(self, cluster: dict) -> dict:
        """Deploy menggunakan Docker Stack kantin-stack.yml (Tugas 6 Tantangan)."""
        logger.info("=== DEPLOY APPKANTIN MENGGUNAKAN DOCKER STACK (TUGAS 6 TANTANGAN) ===")
        mgr_id = cluster["manager"]["instance_id"]

        cmds = [
            "docker service rm kantin 2>/dev/null || true",
            "sleep 3",
            """cat << 'EOF' > /home/ubuntu/kantin-stack.yml
services:
  web:
    image: trafex/php-nginx
    ports:
      - "8080:8080"
    volumes:
      - /home/ubuntu/appKantin:/var/www/html
    deploy:
      replicas: 3
EOF""",
            "docker stack deploy -c /home/ubuntu/kantin-stack.yml kantin",
            "sleep 5",
            "docker stack services kantin",
            "docker stack ps kantin"
        ]
        res = self.execute_ssm(mgr_id, cmds)
        logger.info("Hasil Deploy Docker Stack:\n" + res["stdout"])
        return {"output": res["stdout"]}

    def verify_all(self, cluster: dict) -> dict:
        """Verifikasi menyeluruh klaster Swarm, DB, dan akses HTTP (Non-destruktif)."""
        logger.info("=== VERIFIKASI MENYELURUH LKPD 8 ===")
        mgr_id = cluster["manager"]["instance_id"]
        db_priv = cluster["db"]["private_ip"]

        print("\n" + "="*70)
        print(" [1/5] KEBERADAAN 4 INSTANCE EC2 LKPD 8")
        print("="*70)
        for role in ["manager", "worker1", "worker2", "db"]:
            node = cluster.get(role)
            if node:
                print(f" Node: {role.upper():8} | ID: {node['instance_id']} | Status: {node['state']:7} | Public IP: {node.get('public_ip'):15} | Private IP: {node.get('private_ip')}")
            else:
                print(f" Node: {role.upper():8} | [TIDAK DITEMUKAN]")

        print("\n" + "="*70)
        print(" [2/5] STATUS CLUSTER DOCKER SWARM (LEADER & WORKERS)")
        print("="*70)
        node_res = self.execute_ssm(mgr_id, ["docker node ls"])
        print(node_res.get("stdout", "").strip())

        print("\n" + "="*70)
        print(" [3/5] STATUS SERVICE & DISTRIBUSI REPLIKA TASK")
        print("="*70)
        svc_res = self.execute_ssm(mgr_id, [
            "docker service ls",
            "echo '--- DETAIL TASK SERVICE WEB ---'",
            "docker service ps web 2>/dev/null || true",
            "echo '--- DETAIL TASK SERVICE KANTIN ---'",
            "docker service ps kantin 2>/dev/null || true",
            "docker stack ps kantin 2>/dev/null || true"
        ])
        print(svc_res.get("stdout", "").strip())

        print("\n" + "="*70)
        print(" [4/5] PENGUJIAN AKSES APLIKASI WEB PORT 8080")
        print("="*70)
        http_results = {}
        for role in ["manager", "worker1", "worker2"]:
            pub_ip = cluster[role].get("public_ip")
            if pub_ip and pub_ip != "N/A":
                url = f"http://{pub_ip}:8080/"
                try:
                    import urllib.request
                    req = urllib.request.urlopen(url, timeout=5)
                    code = req.status
                    content = req.read().decode('utf-8', errors='ignore')
                    snippet = [l.strip() for l in content.splitlines() if "<title>" in l or "Hostname" in l or "Aplikasi" in l]
                    info_text = f"HTTP {code} OK | {snippet[0] if snippet else 'Akses Berhasil'}"
                    http_results[role] = {"status": code, "snippet": info_text}
                    print(f" Akses [{role.upper()}] ({url}): {info_text}")
                except Exception as e:
                    http_results[role] = {"status": "Error", "error": str(e)}
                    print(f" Akses [{role.upper()}] ({url}): Gagal ({e})")

        print("\n" + "="*70)
        print(" [5/5] KONEKSI & KONFIGURASI BASIS DATA EKSTERNAL (MARIADB)")
        print("="*70)
        db_check_cmds = [
            f"docker run --rm -e MYSQL_PWD=rahasia mariadb:11.8 mariadb -h {db_priv} -uroot -e 'SELECT VERSION(); SHOW DATABASES;' 2>/dev/null || echo 'DB_CONN_FAILED'",
            f"docker run --rm -e MYSQL_PWD=rahasia mariadb:11.8 mariadb -h {db_priv} -uroot -e 'USE kantin_db; SHOW TABLES; SELECT COUNT(*) FROM menu;' 2>/dev/null || echo 'CATATAN: kantin_db belum dibuat (Tugas 3-5 belum dijalankan)'"
        ]
        db_res = self.execute_ssm(mgr_id, db_check_cmds)
        print(db_res.get("stdout", "").strip())
        print("="*70 + "\n")

        return {
            "cluster": cluster,
            "nodes": node_res.get("stdout", ""),
            "services": svc_res.get("stdout", ""),
            "http": http_results,
            "database": db_res.get("stdout", "")
        }

    def cleanup(self, cluster: dict):
        """Membersihkan service dan stack."""
        logger.info("Membersihkan seluruh service dan stack di swarm manager...")
        mgr_id = cluster["manager"]["instance_id"]
        self.execute_ssm(mgr_id, [
            "docker service rm web 2>/dev/null || true",
            "docker service rm kantin 2>/dev/null || true",
            "docker stack rm kantin 2>/dev/null || true"
        ])

    def terminate_cluster(self, cluster: dict):
        """Menghapus seluruh 4 instance EC2 LKPD 8."""
        ids = [v["instance_id"] for v in cluster.values() if v]
        if ids:
            logger.info(f"Menghentikan dan menghapus instance: {ids}")
            terminate_instances(ids)
