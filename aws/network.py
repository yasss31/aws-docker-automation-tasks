import logging
import boto3
from botocore.exceptions import ClientError
from config.settings import settings
from aws.ami import get_session

logger = logging.getLogger(__name__)

def resolve_default_vpc_and_subnet():
    session = get_session()
    ec2 = session.client("ec2")

    vpc_id = settings.VPC_ID
    subnet_id = settings.SUBNET_ID

    if not vpc_id:
        res = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        vpcs = res.get("Vpcs", [])
        if not vpcs:
            raise RuntimeError("Default VPC tidak ditemukan di region ini. Mohon tentukan VPC_ID di .env.")
        vpc_id = vpcs[0]["VpcId"]
        logger.info(f"Menggunakan Default VPC: {vpc_id}")
    else:
        logger.info(f"Menggunakan VPC dari konfigurasi: {vpc_id}")

    if not subnet_id:
        res = ec2.describe_subnets(Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "default-for-az", "Values": ["true"]}
        ])
        subnets = res.get("Subnets", [])
        if not subnets:
            res = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
            subnets = res.get("Subnets", [])
        if not subnets:
            raise RuntimeError(f"Tidak ditemukan Subnet untuk VPC {vpc_id}.")
        subnet_id = subnets[0]["SubnetId"]
        logger.info(f"Menggunakan Subnet: {subnet_id} (AZ: {subnets[0].get('AvailabilityZone')})")
    else:
        logger.info(f"Menggunakan Subnet dari konfigurasi: {subnet_id}")

    return vpc_id, subnet_id

def resolve_or_create_security_group(vpc_id: str) -> str:
    session = get_session()
    ec2 = session.client("ec2")

    if settings.SECURITY_GROUP_ID:
        logger.info(f"Menggunakan Security Group yang ditentukan: {settings.SECURITY_GROUP_ID}")
        return settings.SECURITY_GROUP_ID

    sg_name = settings.SECURITY_GROUP_NAME
    logger.info(f"Mencari Security Group {sg_name} di VPC {vpc_id}...")
    try:
        res = ec2.describe_security_groups(Filters=[
            {"Name": "group-name", "Values": [sg_name]},
            {"Name": "vpc-id", "Values": [vpc_id]}
        ])
        sgs = res.get("SecurityGroups", [])
        if sgs:
            sg_id = sgs[0]["GroupId"]
            logger.info(f"Security Group ditemukan: {sg_id}")
            sync_sg_rules(ec2, sg_id)
            return sg_id
    except ClientError as e:
        logger.warning(f"Error saat cek SG: {e}")

    logger.info(f"Membuat Security Group baru: {sg_name}...")
    try:
        res = ec2.create_security_group(
            GroupName=sg_name,
            Description="Security Group bersama untuk AWS LKPD Docker Automation",
            VpcId=vpc_id,
            TagSpecifications=[{
                "ResourceType": "security-group",
                "Tags": [
                    {"Key": "Name", "Value": sg_name},
                    {"Key": "Project", "Value": settings.PROJECT_NAME}
                ]
            }]
        )
        sg_id = res["GroupId"]
        logger.info(f"Security Group berhasil dibuat: {sg_id}")
        sync_sg_rules(ec2, sg_id)
        return sg_id
    except ClientError as e:
        raise RuntimeError(f"Gagal membuat Security Group {sg_name}: {e}")

def sync_sg_rules(ec2, sg_id: str):
    logger.info(f"Sinkronisasi Inbound Rules pada SG {sg_id}...")
    rules_to_add = settings.parse_sg_rules()
    
    try:
        res = ec2.describe_security_groups(GroupIds=[sg_id])
        existing_sg = res['SecurityGroups'][0]
        existing_ports = set()
        for perm in existing_sg.get('IpPermissions', []):
            from_p = perm.get('FromPort')
            for r in perm.get('IpRanges', []):
                existing_ports.add((from_p, r.get('CidrIp')))
    except Exception as e:
        logger.warning(f"Gagal inspect existing SG rules: {e}")
        existing_ports = set()

    for port, cidr in rules_to_add:
        if (port, cidr) in existing_ports:
            continue
        try:
            ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[{
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort": port,
                    "IpRanges": [{"CidrIp": cidr, "Description": f"LKPD automation port {port}"}]
                }]
            )
            logger.info(f"Berhasil menambahkan Inbound Rule port {port} ({cidr}).")
        except ClientError as e:
            if "InvalidPermission.Duplicate" not in str(e):
                logger.warning(f"Catatan sinkronisasi SG Rule port {port}: {e}")

