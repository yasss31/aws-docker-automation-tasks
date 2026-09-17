import logging
import time
import json
import os
import boto3
from botocore.exceptions import ClientError
from config.settings import settings
from aws.ami import get_session

logger = logging.getLogger(__name__)

def validate_key_pair(key_name: str):
    session = get_session()
    ec2 = session.client("ec2")
    try:
        res = ec2.describe_key_pairs(KeyNames=[key_name])
        logger.info(f"Key Pair valid: {key_name}")
        return True
    except ClientError as e:
        raise RuntimeError(f"Key Pair '{key_name}' tidak ditemukan di region {settings.AWS_REGION}: {e}")

def validate_iam_instance_profile(profile_name: str):
    session = get_session()
    iam = session.client("iam")
    try:
        res = iam.get_instance_profile(InstanceProfileName=profile_name)
        arn = res["InstanceProfile"]["Arn"]
        logger.info(f"IAM Instance Profile valid: {profile_name} ({arn})")
        return arn
    except ClientError as e:
        raise RuntimeError(f"IAM Instance Profile '{profile_name}' tidak ditemukan di akun AWS ini: {e}")

def launch_ec2_instance(lkpd_num: int, lkpd_name: str, ami_id: str, subnet_id: str, sg_id: str, user_data_script: str, custom_name: str = None, task_name: str = None) -> str:
    session = get_session()
    ec2 = session.client("ec2")

    instance_name = custom_name if custom_name else f"lkpd-{lkpd_num}-{lkpd_name}"
    display_label = f"Tugas {task_name}" if task_name else f"LKPD {lkpd_num}"
    logger.info(f"Meluncurkan instance EC2 untuk {display_label}: {instance_name}...")

    tags = [
        {"Key": "Name", "Value": instance_name},
        {"Key": "Project", "Value": settings.PROJECT_NAME},
        {"Key": "LKPD", "Value": str(lkpd_num)},
        {"Key": "Task", "Value": task_name if task_name else "lkpd"},
        {"Key": "ManagedBy", "Value": "aws-lkpd-automation"}
    ]

    iam_param = {}
    if settings.EC2_IAM_INSTANCE_PROFILE:
        iam_param = {"IamInstanceProfile": {"Name": settings.EC2_IAM_INSTANCE_PROFILE}}

    try:
        res = ec2.run_instances(
            ImageId=ami_id,
            InstanceType=settings.EC2_INSTANCE_TYPE,
            KeyName=settings.EC2_KEY_NAME,
            MinCount=1,
            MaxCount=1,
            SubnetId=subnet_id,
            SecurityGroupIds=[sg_id],
            UserData=user_data_script,
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": tags
            }],
            **iam_param
        )
        instance_id = res["Instances"][0]["InstanceId"]
        logger.info(f"Instance berhasil diluncurkan dengan ID: {instance_id}")
        return instance_id
    except ClientError as e:
        raise RuntimeError(f"Gagal meluncurkan EC2 untuk {display_label}: {e}")

def wait_for_instance_running(instance_id: str, timeout_seconds: int = 300) -> dict:
    session = get_session()
    ec2 = session.client("ec2")
    logger.info(f"Menunggu instance {instance_id} running...")

    start = time.time()
    while time.time() - start < timeout_seconds:
        res = ec2.describe_instances(InstanceIds=[instance_id])
        inst = res["Reservations"][0]["Instances"][0]
        state = inst["State"]["Name"]
        if state == "running":
            pub_ip = inst.get("PublicIpAddress", "N/A")
            pub_dns = inst.get("PublicDnsName", "N/A")
            logger.info(f"Instance {instance_id} Running! Public IP: {pub_ip}, DNS: {pub_dns}")
            return {
                "instance_id": instance_id,
                "public_ip": pub_ip,
                "public_dns": pub_dns,
                "state": state
            }
        elif state in ("terminated", "shutting-down"):
            raise RuntimeError(f"Instance {instance_id} beralih ke state gagal: {state}")
        time.sleep(10)

    raise TimeoutError(f"Timeout menunggu instance {instance_id} running.")

def get_instances_status(lkpd_filter: int = None, task_filter: str = None) -> list:
    session = get_session()
    ec2 = session.client("ec2")

    filters = [
        {"Name": "tag:Project", "Values": [settings.PROJECT_NAME]},
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}
    ]
    if lkpd_filter:
        filters.append({"Name": "tag:LKPD", "Values": [str(lkpd_filter)]})
    if task_filter:
        filters.append({"Name": "tag:Task", "Values": [str(task_filter)]})

    res = ec2.describe_instances(Filters=filters)
    results = []
    for r in res.get("Reservations", []):
        for inst in r.get("Instances", []):
            name = "N/A"
            lkpd_num = "N/A"
            task_type = "lkpd"
            for t in inst.get("Tags", []):
                if t["Key"] == "Name":
                    name = t["Value"]
                if t["Key"] == "LKPD":
                    lkpd_num = t["Value"]
                if t["Key"] == "Task":
                    task_type = t["Value"]
            results.append({
                "lkpd": lkpd_num,
                "task": task_type,
                "name": name,
                "instance_id": inst["InstanceId"],
                "state": inst["State"]["Name"],
                "public_ip": inst.get("PublicIpAddress", "-"),
                "launch_time": str(inst["LaunchTime"])
            })
    results.sort(key=lambda x: str(x.get("name", "")))
    return results

def terminate_instances(lkpd_filter: int = None, task_filter: str = None) -> list:
    session = get_session()
    ec2 = session.client("ec2")

    active_instances = get_instances_status(lkpd_filter=lkpd_filter, task_filter=task_filter)
    if not active_instances:
        logger.info("Tidak ada instance aktif yang cocok untuk di-terminate.")
        return []

    target_ids = [i["instance_id"] for i in active_instances]
    logger.info(f"Menghentikan / terminate instance: {target_ids}")
    ec2.terminate_instances(InstanceIds=target_ids)
    return target_ids
