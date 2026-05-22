import os
import json
from typing import Optional

import boto3
import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("AWS MCP Server")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ec2(region: Optional[str] = None):
    return boto3.client(
        "ec2",
        region_name=region or os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )


def _get_my_ip() -> str:
    for url in [
        "https://api.ipify.org?format=json",
        "https://checkip.amazonaws.com",
    ]:
        try:
            r = requests.get(url, timeout=5)
            if "ipify" in url:
                return r.json()["ip"]
            return r.text.strip()
        except Exception:
            continue
    raise RuntimeError("Unable to retrieve current public IP.")


def _name_tag(tags) -> str:
    if not tags:
        return ""
    for t in tags:
        if t["Key"] == "Name":
            return t["Value"]
    return ""


def _fmt_rules(rules: list) -> list:
    out = []
    for r in rules:
        proto = r.get("IpProtocol", "")
        from_port = r.get("FromPort", "ALL")
        to_port = r.get("ToPort", "ALL")
        port_str = f"{from_port}" if from_port == to_port else f"{from_port}-{to_port}"
        if proto == "-1":
            proto = "ALL"
            port_str = "ALL"
        cidrs = [c["CidrIp"] for c in r.get("IpRanges", [])]
        cidrs += [c["CidrIpv6"] for c in r.get("Ipv6Ranges", [])]
        out.append({"protocol": proto, "port": port_str, "cidr": cidrs, "desc": r.get("Description", "")})
    return out


# ---------------------------------------------------------------------------
# Security Group tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_security_groups(region: str = "ap-northeast-2") -> str:
    """List all security groups in the AWS account with inbound and outbound rules."""
    ec2 = _ec2(region)
    resp = ec2.describe_security_groups()
    result = []
    for sg in resp["SecurityGroups"]:
        result.append({
            "id": sg["GroupId"],
            "name": sg["GroupName"],
            "description": sg["Description"],
            "vpc_id": sg.get("VpcId", ""),
            "inbound_rules": _fmt_rules(sg.get("IpPermissions", [])),
            "outbound_rules": _fmt_rules(sg.get("IpPermissionsEgress", [])),
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_my_public_ip() -> str:
    """Return the current public IP address of this machine."""
    ip = _get_my_ip()
    return json.dumps({"public_ip": ip})


@mcp.tool()
def add_my_ip_to_security_group(
    security_group_id: str,
    port: int,
    protocol: str = "tcp",
    description: str = "Added by AWS MCP",
    region: str = "ap-northeast-2",
) -> str:
    """Add the current public IP as an inbound rule to the specified security group.

    Args:
        security_group_id: Security group ID (e.g. sg-0abc1234)
        port: Port number to allow (e.g. 22, 3389, 443)
        protocol: Protocol (tcp / udp / icmp)
        description: Rule description
        region: AWS region
    """
    ip = _get_my_ip()
    cidr = f"{ip}/32"
    ec2 = _ec2(region)
    try:
        ec2.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[{
                "IpProtocol": protocol,
                "FromPort": port,
                "ToPort": port,
                "IpRanges": [{"CidrIp": cidr, "Description": description}],
            }],
        )
        return json.dumps({
            "status": "success",
            "message": f"Added {cidr} to {security_group_id} on port {port}/{protocol}",
            "ip": ip,
        }, ensure_ascii=False)
    except ec2.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "InvalidPermission.Duplicate":
            return json.dumps({"status": "already_exists", "message": f"{cidr} already exists in the rule set.", "ip": ip}, ensure_ascii=False)
        raise


@mcp.tool()
def remove_ip_from_security_group(
    security_group_id: str,
    cidr: str,
    port: int,
    protocol: str = "tcp",
    region: str = "ap-northeast-2",
) -> str:
    """Remove a specific CIDR IP rule from a security group.

    Args:
        security_group_id: Security group ID
        cidr: CIDR to remove (e.g. 1.2.3.4/32)
        port: Port number
        protocol: Protocol (tcp / udp)
        region: AWS region
    """
    ec2 = _ec2(region)
    ec2.revoke_security_group_ingress(
        GroupId=security_group_id,
        IpPermissions=[{
            "IpProtocol": protocol,
            "FromPort": port,
            "ToPort": port,
            "IpRanges": [{"CidrIp": cidr}],
        }],
    )
    return json.dumps({"status": "success", "message": f"Removed {cidr} port {port}/{protocol} rule"}, ensure_ascii=False)


@mcp.tool()
def create_security_group(
    name: str,
    description: str,
    vpc_id: Optional[str] = None,
    region: str = "ap-northeast-2",
) -> str:
    """Create a new security group.

    Args:
        name: Security group name
        description: Security group description
        vpc_id: VPC ID (uses default VPC if not specified)
        region: AWS region
    """
    ec2 = _ec2(region)
    kwargs = {"GroupName": name, "Description": description}
    if vpc_id:
        kwargs["VpcId"] = vpc_id
    resp = ec2.create_security_group(**kwargs)
    sg_id = resp["GroupId"]
    ec2.create_tags(Resources=[sg_id], Tags=[{"Key": "Name", "Value": name}])
    return json.dumps({"status": "success", "security_group_id": sg_id, "name": name}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# EC2 Instance tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_ec2_instances(
    region: str = "ap-northeast-2",
    state: str = "all",
) -> str:
    """List EC2 instances with their state, IP addresses, and instance type.

    Args:
        region: AWS region
        state: Filter by state (all / running / stopped / pending / terminated)
    """
    ec2 = _ec2(region)
    filters = []
    if state != "all":
        filters = [{"Name": "instance-state-name", "Values": [state]}]
    resp = ec2.describe_instances(Filters=filters)
    result = []
    for reservation in resp["Reservations"]:
        for inst in reservation["Instances"]:
            result.append({
                "instance_id": inst["InstanceId"],
                "name": _name_tag(inst.get("Tags")),
                "state": inst["State"]["Name"],
                "instance_type": inst["InstanceType"],
                "public_ip": inst.get("PublicIpAddress", ""),
                "private_ip": inst.get("PrivateIpAddress", ""),
                "ami_id": inst["ImageId"],
                "key_name": inst.get("KeyName", ""),
                "launch_time": inst["LaunchTime"].isoformat(),
                "security_groups": [
                    {"id": sg["GroupId"], "name": sg["GroupName"]}
                    for sg in inst.get("SecurityGroups", [])
                ],
                "subnet_id": inst.get("SubnetId", ""),
                "vpc_id": inst.get("VpcId", ""),
            })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_instance_details(
    instance_id: str,
    region: str = "ap-northeast-2",
) -> str:
    """Get detailed information about a specific EC2 instance.

    Args:
        instance_id: Instance ID (e.g. i-0abc1234)
        region: AWS region
    """
    ec2 = _ec2(region)
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    inst = resp["Reservations"][0]["Instances"][0]
    detail = {
        "instance_id": inst["InstanceId"],
        "name": _name_tag(inst.get("Tags")),
        "state": inst["State"]["Name"],
        "instance_type": inst["InstanceType"],
        "public_ip": inst.get("PublicIpAddress", ""),
        "private_ip": inst.get("PrivateIpAddress", ""),
        "public_dns": inst.get("PublicDnsName", ""),
        "ami_id": inst["ImageId"],
        "key_name": inst.get("KeyName", ""),
        "launch_time": inst["LaunchTime"].isoformat(),
        "availability_zone": inst["Placement"]["AvailabilityZone"],
        "security_groups": [
            {"id": sg["GroupId"], "name": sg["GroupName"]}
            for sg in inst.get("SecurityGroups", [])
        ],
        "subnet_id": inst.get("SubnetId", ""),
        "vpc_id": inst.get("VpcId", ""),
        "tags": inst.get("Tags", []),
        "monitoring": inst.get("Monitoring", {}).get("State", ""),
        "iam_profile": inst.get("IamInstanceProfile", {}).get("Arn", ""),
    }
    return json.dumps(detail, ensure_ascii=False, indent=2)


@mcp.tool()
def start_ec2_instance(
    instance_id: str,
    region: str = "ap-northeast-2",
) -> str:
    """Start a stopped EC2 instance.

    Args:
        instance_id: Instance ID
        region: AWS region
    """
    ec2 = _ec2(region)
    resp = ec2.start_instances(InstanceIds=[instance_id])
    state = resp["StartingInstances"][0]["CurrentState"]["Name"]
    return json.dumps({"status": "success", "instance_id": instance_id, "current_state": state}, ensure_ascii=False)


@mcp.tool()
def stop_ec2_instance(
    instance_id: str,
    region: str = "ap-northeast-2",
) -> str:
    """Stop a running EC2 instance.

    Args:
        instance_id: Instance ID
        region: AWS region
    """
    ec2 = _ec2(region)
    resp = ec2.stop_instances(InstanceIds=[instance_id])
    state = resp["StoppingInstances"][0]["CurrentState"]["Name"]
    return json.dumps({"status": "success", "instance_id": instance_id, "current_state": state}, ensure_ascii=False)


@mcp.tool()
def reboot_ec2_instance(
    instance_id: str,
    region: str = "ap-northeast-2",
) -> str:
    """Reboot an EC2 instance.

    Args:
        instance_id: Instance ID
        region: AWS region
    """
    ec2 = _ec2(region)
    ec2.reboot_instances(InstanceIds=[instance_id])
    return json.dumps({"status": "success", "message": f"Reboot requested for {instance_id}"}, ensure_ascii=False)


@mcp.tool()
def create_ec2_instance(
    ami_id: str,
    instance_type: str,
    key_name: str,
    security_group_ids: str,
    name: str = "",
    subnet_id: str = "",
    region: str = "ap-northeast-2",
    user_data: str = "",
) -> str:
    """Launch a new EC2 instance.

    Args:
        ami_id: AMI ID (e.g. ami-0c2d3e23e757b5d84)
        instance_type: Instance type (e.g. t3.micro, t3.small)
        key_name: Key pair name
        security_group_ids: Security group IDs, comma-separated (e.g. sg-111,sg-222)
        name: Instance name tag
        subnet_id: Subnet ID (uses default subnet if not specified)
        region: AWS region
        user_data: Shell script to run on launch (optional)
    """
    ec2 = _ec2(region)
    sg_ids = [s.strip() for s in security_group_ids.split(",") if s.strip()]
    kwargs = {
        "ImageId": ami_id,
        "InstanceType": instance_type,
        "KeyName": key_name,
        "SecurityGroupIds": sg_ids,
        "MinCount": 1,
        "MaxCount": 1,
    }
    if subnet_id:
        kwargs["SubnetId"] = subnet_id
    if user_data:
        kwargs["UserData"] = user_data

    tags = [{"Key": "Name", "Value": name}] if name else []
    if tags:
        kwargs["TagSpecifications"] = [{"ResourceType": "instance", "Tags": tags}]

    resp = ec2.run_instances(**kwargs)
    inst = resp["Instances"][0]
    return json.dumps({
        "status": "success",
        "instance_id": inst["InstanceId"],
        "state": inst["State"]["Name"],
        "instance_type": inst["InstanceType"],
        "ami_id": inst["ImageId"],
        "private_ip": inst.get("PrivateIpAddress", ""),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def terminate_ec2_instance(
    instance_id: str,
    region: str = "ap-northeast-2",
) -> str:
    """Permanently terminate (delete) an EC2 instance. This action is irreversible.

    Args:
        instance_id: Instance ID to terminate
        region: AWS region
    """
    ec2 = _ec2(region)
    resp = ec2.terminate_instances(InstanceIds=[instance_id])
    state = resp["TerminatingInstances"][0]["CurrentState"]["Name"]
    return json.dumps({"status": "success", "instance_id": instance_id, "current_state": state}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# VPC / Subnet / Key Pair tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_key_pairs(region: str = "ap-northeast-2") -> str:
    """List available EC2 key pairs."""
    ec2 = _ec2(region)
    resp = ec2.describe_key_pairs()
    result = [{"name": kp["KeyName"], "fingerprint": kp.get("KeyFingerprint", ""), "id": kp.get("KeyPairId", "")} for kp in resp["KeyPairs"]]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_vpcs(region: str = "ap-northeast-2") -> str:
    """List VPCs and their associated subnets."""
    ec2 = _ec2(region)
    vpcs_resp = ec2.describe_vpcs()
    subnets_resp = ec2.describe_subnets()
    subnets_by_vpc: dict = {}
    for s in subnets_resp["Subnets"]:
        vid = s["VpcId"]
        subnets_by_vpc.setdefault(vid, []).append({
            "subnet_id": s["SubnetId"],
            "cidr": s["CidrBlock"],
            "az": s["AvailabilityZone"],
            "name": _name_tag(s.get("Tags")),
            "available_ips": s["AvailableIpAddressCount"],
            "public": s.get("MapPublicIpOnLaunch", False),
        })
    result = []
    for vpc in vpcs_resp["Vpcs"]:
        result.append({
            "vpc_id": vpc["VpcId"],
            "cidr": vpc["CidrBlock"],
            "name": _name_tag(vpc.get("Tags")),
            "is_default": vpc.get("IsDefault", False),
            "subnets": subnets_by_vpc.get(vpc["VpcId"], []),
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_available_amis(
    region: str = "ap-northeast-2",
    os_type: str = "amazon-linux",
) -> str:
    """List the latest official AMIs for common OS types.

    Args:
        region: AWS region
        os_type: OS type to query (amazon-linux / ubuntu / windows)
    """
    ec2 = _ec2(region)
    filters_map = {
        "amazon-linux": [
            {"Name": "name", "Values": ["al2023-ami-*-x86_64"]},
            {"Name": "owner-alias", "Values": ["amazon"]},
            {"Name": "state", "Values": ["available"]},
            {"Name": "architecture", "Values": ["x86_64"]},
        ],
        "ubuntu": [
            {"Name": "name", "Values": ["ubuntu/images/hvm-ssd/ubuntu-*-22.04-amd64-server-*"]},
            {"Name": "owner-alias", "Values": ["aws-marketplace"]},
            {"Name": "state", "Values": ["available"]},
        ],
        "windows": [
            {"Name": "name", "Values": ["Windows_Server-2022-English-Full-Base-*"]},
            {"Name": "owner-alias", "Values": ["amazon"]},
            {"Name": "state", "Values": ["available"]},
        ],
    }
    filters = filters_map.get(os_type, filters_map["amazon-linux"])
    resp = ec2.describe_images(Filters=filters)
    images = sorted(resp["Images"], key=lambda x: x["CreationDate"], reverse=True)[:5]
    result = [{"ami_id": img["ImageId"], "name": img["Name"], "created": img["CreationDate"], "description": img.get("Description", "")} for img in images]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_instance_console_output(
    instance_id: str,
    region: str = "ap-northeast-2",
) -> str:
    """Get the system console output (boot log) of an EC2 instance.

    Args:
        instance_id: Instance ID
        region: AWS region
    """
    import base64
    ec2 = _ec2(region)
    resp = ec2.get_console_output(InstanceId=instance_id)
    output = resp.get("Output", "")
    if output:
        try:
            output = base64.b64decode(output).decode("utf-8", errors="replace")
        except Exception:
            pass
    return json.dumps({"instance_id": instance_id, "output": output or "(No output — instance may have started recently or console output is not supported in this state)"}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Elastic IP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_elastic_ips(region: str = "ap-northeast-2") -> str:
    """List allocated Elastic IPs and their associated instance information."""
    ec2 = _ec2(region)
    resp = ec2.describe_addresses()
    result = []
    for addr in resp["Addresses"]:
        result.append({
            "allocation_id": addr.get("AllocationId", ""),
            "public_ip": addr.get("PublicIp", ""),
            "private_ip": addr.get("PrivateIpAddress", ""),
            "instance_id": addr.get("InstanceId", ""),
            "association_id": addr.get("AssociationId", ""),
            "domain": addr.get("Domain", ""),
            "network_interface_id": addr.get("NetworkInterfaceId", ""),
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def allocate_elastic_ip(region: str = "ap-northeast-2") -> str:
    """Allocate a new Elastic IP address."""
    ec2 = _ec2(region)
    resp = ec2.allocate_address(Domain="vpc")
    return json.dumps({
        "status": "success",
        "allocation_id": resp["AllocationId"],
        "public_ip": resp["PublicIp"],
    }, ensure_ascii=False)


@mcp.tool()
def associate_elastic_ip(
    allocation_id: str,
    instance_id: str,
    region: str = "ap-northeast-2",
) -> str:
    """Associate an Elastic IP with an EC2 instance.

    Args:
        allocation_id: EIP allocation ID (e.g. eipalloc-0abc1234)
        instance_id: Instance ID to associate with
        region: AWS region
    """
    ec2 = _ec2(region)
    resp = ec2.associate_address(AllocationId=allocation_id, InstanceId=instance_id)
    return json.dumps({
        "status": "success",
        "association_id": resp["AssociationId"],
        "allocation_id": allocation_id,
        "instance_id": instance_id,
    }, ensure_ascii=False)


@mcp.tool()
def disassociate_elastic_ip(
    association_id: str,
    region: str = "ap-northeast-2",
) -> str:
    """Disassociate an Elastic IP from an instance.

    Args:
        association_id: EIP association ID (e.g. eipassoc-0abc1234)
        region: AWS region
    """
    ec2 = _ec2(region)
    ec2.disassociate_address(AssociationId=association_id)
    return json.dumps({"status": "success", "message": f"Disassociated {association_id}"}, ensure_ascii=False)


@mcp.tool()
def release_elastic_ip(
    allocation_id: str,
    region: str = "ap-northeast-2",
) -> str:
    """Release (return) an Elastic IP address. You will no longer own this IP.

    Args:
        allocation_id: EIP allocation ID (e.g. eipalloc-0abc1234)
        region: AWS region
    """
    ec2 = _ec2(region)
    ec2.release_address(AllocationId=allocation_id)
    return json.dumps({"status": "success", "message": f"Released EIP {allocation_id}"}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Convenience tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_ssh_command(
    instance_id: str,
    key_path: str,
    username: str = "",
    region: str = "ap-northeast-2",
) -> str:
    """Generate an SSH command for connecting to an EC2 instance.

    Args:
        instance_id: Instance ID
        key_path: Local path to the PEM key file (e.g. ~/.ssh/my-key.pem)
        username: SSH username (auto-detected from AMI if not specified)
        region: AWS region
    """
    ec2 = _ec2(region)
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    inst = resp["Reservations"][0]["Instances"][0]
    ip = inst.get("PublicIpAddress") or inst.get("PrivateIpAddress", "")
    ami_id = inst.get("ImageId", "")
    state = inst["State"]["Name"]

    if not username:
        try:
            ami_resp = ec2.describe_images(ImageIds=[ami_id])
            ami_name = ami_resp["Images"][0]["Name"].lower() if ami_resp["Images"] else ""
        except Exception:
            ami_name = ""
        if "ubuntu" in ami_name:
            username = "ubuntu"
        elif "centos" in ami_name:
            username = "centos"
        elif "rhel" in ami_name or "red hat" in ami_name:
            username = "ec2-user"
        elif "debian" in ami_name:
            username = "admin"
        elif "windows" in ami_name:
            username = "Administrator"
        else:
            username = "ec2-user"

    cmd = f"ssh -i {key_path} {username}@{ip}"
    return json.dumps({
        "command": cmd,
        "instance_id": instance_id,
        "ip": ip,
        "username": username,
        "state": state,
        "note": "No public IP — connect via VPN or Bastion using the private IP." if not inst.get("PublicIpAddress") else "",
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def add_instance_tag(
    instance_id: str,
    key: str,
    value: str,
    region: str = "ap-northeast-2",
) -> str:
    """Add or update a tag on an EC2 instance.

    Args:
        instance_id: Instance ID
        key: Tag key (e.g. Name, Env, Owner)
        value: Tag value (e.g. my-server, production, john)
        region: AWS region
    """
    ec2 = _ec2(region)
    ec2.create_tags(Resources=[instance_id], Tags=[{"Key": key, "Value": value}])
    return json.dumps({"status": "success", "instance_id": instance_id, "tag": {key: value}}, ensure_ascii=False)


@mcp.tool()
def change_instance_type(
    instance_id: str,
    new_instance_type: str,
    region: str = "ap-northeast-2",
) -> str:
    """Change the instance type of an EC2 instance. Automatically stops the instance if running.

    Args:
        instance_id: Instance ID
        new_instance_type: Target instance type (e.g. t3.medium, c5.large)
        region: AWS region
    """
    ec2 = _ec2(region)
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    inst = resp["Reservations"][0]["Instances"][0]
    current_state = inst["State"]["Name"]
    current_type = inst["InstanceType"]

    steps = []
    if current_state == "running":
        ec2.stop_instances(InstanceIds=[instance_id])
        waiter = ec2.get_waiter("instance_stopped")
        waiter.wait(InstanceIds=[instance_id])
        steps.append("Instance stopped")

    ec2.modify_instance_attribute(
        InstanceId=instance_id,
        InstanceType={"Value": new_instance_type},
    )
    steps.append(f"Type changed: {current_type} -> {new_instance_type}")

    if current_state == "running":
        ec2.start_instances(InstanceIds=[instance_id])
        steps.append("Instance restarted")

    return json.dumps({
        "status": "success",
        "instance_id": instance_id,
        "previous_type": current_type,
        "new_type": new_instance_type,
        "steps": steps,
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# S3 tools
# ---------------------------------------------------------------------------

def _s3(region: Optional[str] = None):
    return boto3.client(
        "s3",
        region_name=region or os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )


@mcp.tool()
def list_s3_buckets() -> str:
    """List all S3 buckets with their creation date and region."""
    s3 = _s3()
    resp = s3.list_buckets()
    result = []
    for b in resp.get("Buckets", []):
        try:
            loc = s3.get_bucket_location(Bucket=b["Name"])
            region = loc.get("LocationConstraint") or "us-east-1"
        except Exception:
            region = "unknown"
        result.append({
            "name": b["Name"],
            "created": b["CreationDate"].isoformat(),
            "region": region,
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_s3_objects(
    bucket: str,
    prefix: str = "",
    max_keys: int = 50,
) -> str:
    """List objects in an S3 bucket.

    Args:
        bucket: S3 bucket name
        prefix: Path filter (e.g. logs/ or 2024/)
        max_keys: Maximum number of results to return (default 50)
    """
    s3 = _s3()
    kwargs = {"Bucket": bucket, "MaxKeys": max_keys}
    if prefix:
        kwargs["Prefix"] = prefix
    resp = s3.list_objects_v2(**kwargs)
    objects = resp.get("Contents", [])
    result = [
        {
            "key": o["Key"],
            "size_bytes": o["Size"],
            "size_readable": f"{o['Size'] / 1024:.1f} KB" if o["Size"] < 1024 * 1024 else f"{o['Size'] / 1024 / 1024:.1f} MB",
            "last_modified": o["LastModified"].isoformat(),
        }
        for o in objects
    ]
    return json.dumps({
        "bucket": bucket,
        "prefix": prefix,
        "count": len(result),
        "truncated": resp.get("IsTruncated", False),
        "objects": result,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def create_s3_bucket(
    bucket_name: str,
    region: str = "ap-northeast-2",
) -> str:
    """Create a new S3 bucket.

    Args:
        bucket_name: Bucket name (must be globally unique)
        region: AWS region
    """
    s3 = _s3(region)
    kwargs = {"Bucket": bucket_name}
    if region != "us-east-1":
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**kwargs)
    return json.dumps({"status": "success", "bucket": bucket_name, "region": region}, ensure_ascii=False)


@mcp.tool()
def delete_s3_object(
    bucket: str,
    key: str,
) -> str:
    """Delete a specific object from an S3 bucket.

    Args:
        bucket: S3 bucket name
        key: Object key path to delete (e.g. logs/2024/app.log)
    """
    s3 = _s3()
    s3.delete_object(Bucket=bucket, Key=key)
    return json.dumps({"status": "success", "bucket": bucket, "key": key, "message": "Deleted successfully"}, ensure_ascii=False)


@mcp.tool()
def get_s3_presigned_url(
    bucket: str,
    key: str,
    expires_in: int = 3600,
) -> str:
    """Generate a presigned (temporary) download URL for an S3 object.

    Args:
        bucket: S3 bucket name
        key: Object key path (e.g. reports/result.pdf)
        expires_in: URL expiry time in seconds (default 3600 = 1 hour)
    """
    s3 = _s3()
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )
    return json.dumps({
        "url": url,
        "bucket": bucket,
        "key": key,
        "expires_in_seconds": expires_in,
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Bedrock AI tools
# ---------------------------------------------------------------------------

def _bedrock(region: Optional[str] = None):
    return boto3.client(
        "bedrock",
        region_name=region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )


def _bedrock_runtime(region: Optional[str] = None):
    return boto3.client(
        "bedrock-runtime",
        region_name=region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )


@mcp.tool()
def list_bedrock_models(
    region: str = "us-east-1",
    provider: str = "",
) -> str:
    """List available foundation models on AWS Bedrock.

    Args:
        region: AWS region (us-east-1 or us-west-2 recommended for Bedrock)
        provider: Provider filter (e.g. Anthropic, Amazon, Meta, Mistral AI — leave blank for all)
    """
    bedrock = _bedrock(region)
    kwargs = {"byOutputModality": "TEXT"}
    if provider:
        kwargs["byProvider"] = provider
    resp = bedrock.list_foundation_models(**kwargs)
    result = []
    for m in resp.get("modelSummaries", []):
        result.append({
            "model_id": m["modelId"],
            "model_name": m["modelName"],
            "provider": m["providerName"],
            "input_modalities": m.get("inputModalities", []),
            "output_modalities": m.get("outputModalities", []),
            "response_streaming": m.get("responseStreamingSupported", False),
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def invoke_bedrock_claude(
    prompt: str,
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    max_tokens: int = 1024,
    region: str = "us-east-1",
) -> str:
    """Invoke a Claude model via AWS Bedrock.

    Args:
        prompt: Message to send to the model
        model_id: Bedrock model ID (default: Claude 3.5 Sonnet v2)
        max_tokens: Maximum number of tokens in the response
        region: AWS region
    """
    runtime = _bedrock_runtime(region)
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    })
    resp = runtime.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(resp["body"].read())
    text = result.get("content", [{}])[0].get("text", "")
    return json.dumps({
        "model_id": model_id,
        "response": text,
        "input_tokens": result.get("usage", {}).get("input_tokens", 0),
        "output_tokens": result.get("usage", {}).get("output_tokens", 0),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def invoke_bedrock_model_raw(
    model_id: str,
    body: str,
    region: str = "us-east-1",
) -> str:
    """Invoke any Bedrock model with a raw JSON body. Use for non-Claude models (Titan, Llama, etc.).

    Args:
        model_id: Bedrock model ID
        body: Request JSON string in the model's expected format
        region: AWS region
    """
    runtime = _bedrock_runtime(region)
    resp = runtime.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(resp["body"].read())
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_bedrock_knowledge_bases(region: str = "us-east-1") -> str:
    """List Bedrock Knowledge Bases."""
    agent_client = boto3.client(
        "bedrock-agent",
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )
    resp = agent_client.list_knowledge_bases()
    result = []
    for kb in resp.get("knowledgeBaseSummaries", []):
        result.append({
            "knowledge_base_id": kb["knowledgeBaseId"],
            "name": kb["name"],
            "status": kb["status"],
            "description": kb.get("description", ""),
            "updated_at": kb["updatedAt"].isoformat(),
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def query_bedrock_knowledge_base(
    knowledge_base_id: str,
    query: str,
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    region: str = "us-east-1",
) -> str:
    """Query a Bedrock Knowledge Base and get a RAG-based answer.

    Args:
        knowledge_base_id: Knowledge Base ID
        query: Question to ask
        model_id: Model ID to use for generating the answer
        region: AWS region
    """
    agent_runtime = boto3.client(
        "bedrock-agent-runtime",
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )
    resp = agent_runtime.retrieve_and_generate(
        input={"text": query},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": knowledge_base_id,
                "modelArn": f"arn:aws:bedrock:{region}::foundation-model/{model_id}",
            },
        },
    )
    output = resp.get("output", {}).get("text", "")
    citations = [
        {
            "text": c.get("generatedResponsePart", {}).get("textResponsePart", {}).get("text", ""),
            "sources": [
                ref.get("location", {}).get("s3Location", {}).get("uri", "")
                for ref in c.get("retrievedReferences", [])
            ],
        }
        for c in resp.get("citations", [])
    ]
    return json.dumps({
        "answer": output,
        "citations": citations,
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
