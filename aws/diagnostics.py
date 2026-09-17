import sys, os
sys.path.insert(0, r'D:\LKPD\aws-lkpd-automation')
import boto3, time, json
import urllib.request
from aws.ami import get_session
from aws.ec2 import get_instances_status

def inspect_all():
    print("\n" + "="*85)
    print("LAPORAN DETEKSI & INSPEKSI STATUS RUNTIME EC2 LKPD (LIVE)")
    print("="*85)

    session = get_session()
    ssm = session.client("ssm")

    instances = get_instances_status()
    if not instances:
        print("Tidak ada instance yang sedang aktif di akun AWS Anda.")
        return

    PORT_MAP = {
        "1": 8080,
        "2": 8088,
        "3": 8001,
        "4": 8002,
        "5": 8088,
        "tugas2": 8080,
        "tugas3": 8083
    }

    for inst in instances:
        lkpd_num = str(inst.get("lkpd", "?"))
        task_type = inst.get("task", "lkpd")
        inst_name = inst.get("name", "")
        inst_id = inst["instance_id"]
        pub_ip = inst.get("public_ip", "-")

        if task_type == "tugas3" or "tugas-3" in inst_name.lower():
            expected_port = 8083
            label = f"TUGAS 3: {inst_name}"
        elif task_type == "tugas2" or "tugas" in inst_name.lower():
            expected_port = 8080
            label = f"TUGAS 2: {inst_name}"
        else:
            expected_port = PORT_MAP.get(lkpd_num, 80)
            label = f"LKPD {lkpd_num}: {inst_name}"

        url = f"http://{pub_ip}:{expected_port}" if pub_ip != "-" else "-"

        print(f"\n[+] {label} ({inst_id})")
        print(f"    - EC2 State      : {inst['state']}")
        print(f"    - Public IP      : {pub_ip}")
        print(f"    - Target URL     : {url}")

        # 1. Pengecekan Akses Port & Respon HTTP dari Luar
        http_result = "N/A"
        if pub_ip != "-":
            try:
                req = urllib.request.urlopen(url, timeout=3)
                http_result = f"HTTP {req.status} OK (Tersedia untuk Penguji)"
            except Exception as e:
                http_result = f"Koneksi Gagal / Menunggu ({e})"
        print(f"    - HTTP Access    : {http_result}")

        # 2. Pengecekan Langsung ke Dalam Mesin via SSM
        print("    - Diagnosa Dalam Server (via SSM):")
        try:
            cmd = ssm.send_command(
                InstanceIds=[inst_id],
                DocumentName="AWS-RunShellScript",
                Parameters={"commands": [
                    "echo '---STATUS_JSON_START---'",
                    "cat /opt/lkpd/status.json 2>/dev/null || echo '{\"status\":\"no_status\"}'",
                    "echo '---STATUS_JSON_END---'",
                    "docker ps -a --format '{{.Names}}|{{.Status}}|{{.Ports}}'"
                ]}
            )
            cmd_id = cmd["Command"]["CommandId"]
            time.sleep(2)
            out = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=inst_id)
            stdout = out.get("StandardOutputContent", "")

            # Parsing status JSON
            st_val = "UNKNOWN"
            st_stage = "-"
            st_msg = "-"
            if "---STATUS_JSON_START---" in stdout and "---STATUS_JSON_END---" in stdout:
                parts = stdout.split("---STATUS_JSON_START---")[1].split("---STATUS_JSON_END---")
                json_raw = parts[0].strip()
                container_raw = parts[1].strip()
                try:
                    st = json.loads(json_raw)
                    st_val = st.get("status", "unknown").upper()
                    st_stage = st.get("stage", "-")
                    st_msg = st.get("message", "-")
                except:
                    pass
            else:
                container_raw = stdout.strip()

            print(f"      * Status LKPD : {st_val} (Stage: {st_stage})")
            print(f"      * Keterangan  : {st_msg}")

            container_lines = [l for l in container_raw.splitlines() if l.strip() and "|" in l]
            if container_lines:
                print("      * Kontainer Docker Aktif:")
                for c in container_lines:
                    parts = c.split("|")
                    c_name = parts[0] if len(parts) > 0 else "-"
                    c_stat = parts[1] if len(parts) > 1 else "-"
                    c_port = parts[2] if len(parts) > 2 else "-"
                    print(f"        - {c_name:<15} : {c_stat} (Port: {c_port})")
            else:
                print("      * Kontainer Docker : Belum ada kontainer yang berjalan")

        except Exception as err:
            print(f"      * Gagal terhubung via SSM: {err}")

    print("\n" + "="*85 + "\n")

if __name__ == "__main__":
    inspect_all()
