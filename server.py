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
    raise RuntimeError("현재 공인 IP를 가져올 수 없습니다.")


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
    """현재 AWS 계정의 모든 보안그룹 목록과 인바운드/아웃바운드 규칙을 조회합니다."""
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
    """현재 이 서버의 공인 IP 주소를 반환합니다."""
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
    """현재 공인 IP를 지정한 보안그룹의 인바운드 규칙에 추가합니다.

    Args:
        security_group_id: 보안그룹 ID (예: sg-0abc1234)
        port: 허용할 포트 번호 (예: 22, 3389, 443)
        protocol: 프로토콜 (tcp / udp / icmp)
        description: 규칙 설명
        region: AWS 리전
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
            "message": f"{cidr} → {security_group_id} 포트 {port}/{protocol} 추가 완료",
            "ip": ip,
        }, ensure_ascii=False)
    except ec2.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "InvalidPermission.Duplicate":
            return json.dumps({"status": "already_exists", "message": f"{cidr}은 이미 규칙에 존재합니다.", "ip": ip}, ensure_ascii=False)
        raise


@mcp.tool()
def remove_ip_from_security_group(
    security_group_id: str,
    cidr: str,
    port: int,
    protocol: str = "tcp",
    region: str = "ap-northeast-2",
) -> str:
    """보안그룹에서 특정 CIDR IP 규칙을 제거합니다.

    Args:
        security_group_id: 보안그룹 ID
        cidr: 제거할 CIDR (예: 1.2.3.4/32)
        port: 포트 번호
        protocol: 프로토콜 (tcp / udp)
        region: AWS 리전
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
    return json.dumps({"status": "success", "message": f"{cidr} 포트 {port}/{protocol} 규칙 제거 완료"}, ensure_ascii=False)


@mcp.tool()
def create_security_group(
    name: str,
    description: str,
    vpc_id: Optional[str] = None,
    region: str = "ap-northeast-2",
) -> str:
    """새 보안그룹을 생성합니다.

    Args:
        name: 보안그룹 이름
        description: 보안그룹 설명
        vpc_id: VPC ID (None이면 기본 VPC 사용)
        region: AWS 리전
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
    """EC2 인스턴스 목록과 상태, IP, 인스턴스 타입 등을 조회합니다.

    Args:
        region: AWS 리전
        state: 필터 상태 (all / running / stopped / pending / terminated)
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
    """특정 EC2 인스턴스의 상세 정보를 조회합니다.

    Args:
        instance_id: 인스턴스 ID (예: i-0abc1234)
        region: AWS 리전
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
    """중지된 EC2 인스턴스를 시작합니다.

    Args:
        instance_id: 인스턴스 ID
        region: AWS 리전
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
    """실행 중인 EC2 인스턴스를 중지합니다.

    Args:
        instance_id: 인스턴스 ID
        region: AWS 리전
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
    """EC2 인스턴스를 재부팅합니다.

    Args:
        instance_id: 인스턴스 ID
        region: AWS 리전
    """
    ec2 = _ec2(region)
    ec2.reboot_instances(InstanceIds=[instance_id])
    return json.dumps({"status": "success", "message": f"{instance_id} 재부팅 요청 완료"}, ensure_ascii=False)


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
    """새 EC2 인스턴스를 생성합니다.

    Args:
        ami_id: AMI ID (예: ami-0c2d3e23e757b5d84)
        instance_type: 인스턴스 타입 (예: t3.micro, t3.small)
        key_name: 키페어 이름
        security_group_ids: 보안그룹 ID, 여러 개는 쉼표로 구분 (예: sg-111,sg-222)
        name: 인스턴스 이름 태그
        subnet_id: 서브넷 ID (비워두면 기본 서브넷 사용)
        region: AWS 리전
        user_data: 인스턴스 시작 시 실행할 shell 스크립트 (선택)
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
    """EC2 인스턴스를 영구 삭제(terminate)합니다. 되돌릴 수 없습니다.

    Args:
        instance_id: 삭제할 인스턴스 ID
        region: AWS 리전
    """
    ec2 = _ec2(region)
    resp = ec2.terminate_instances(InstanceIds=[instance_id])
    state = resp["TerminatingInstances"][0]["CurrentState"]["Name"]
    return json.dumps({"status": "success", "instance_id": instance_id, "current_state": state}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# VPC / Subnet / Key Pair tools (인스턴스 생성 전 확인용)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_key_pairs(region: str = "ap-northeast-2") -> str:
    """사용 가능한 EC2 키페어 목록을 조회합니다."""
    ec2 = _ec2(region)
    resp = ec2.describe_key_pairs()
    result = [{"name": kp["KeyName"], "fingerprint": kp.get("KeyFingerprint", ""), "id": kp.get("KeyPairId", "")} for kp in resp["KeyPairs"]]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_vpcs(region: str = "ap-northeast-2") -> str:
    """VPC 목록과 서브넷 정보를 조회합니다."""
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
    """자주 사용하는 최신 공식 AMI 목록을 조회합니다.

    Args:
        region: AWS 리전
        os_type: 조회할 OS 타입 (amazon-linux / ubuntu / windows)
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
    """EC2 인스턴스의 시스템 콘솔 출력(부팅 로그)을 가져옵니다.

    Args:
        instance_id: 인스턴스 ID
        region: AWS 리전
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
    return json.dumps({"instance_id": instance_id, "output": output or "(출력 없음 - 인스턴스가 최근 시작되었거나 지원하지 않는 상태일 수 있음)"}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Elastic IP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_elastic_ips(region: str = "ap-northeast-2") -> str:
    """할당된 Elastic IP 목록과 연결된 인스턴스 정보를 조회합니다."""
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
    """새 Elastic IP를 할당합니다."""
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
    """Elastic IP를 EC2 인스턴스에 연결합니다.

    Args:
        allocation_id: EIP 할당 ID (예: eipalloc-0abc1234)
        instance_id: 연결할 인스턴스 ID
        region: AWS 리전
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
    """Elastic IP와 인스턴스의 연결을 해제합니다.

    Args:
        association_id: EIP 연결 ID (예: eipassoc-0abc1234)
        region: AWS 리전
    """
    ec2 = _ec2(region)
    ec2.disassociate_address(AssociationId=association_id)
    return json.dumps({"status": "success", "message": f"{association_id} 연결 해제 완료"}, ensure_ascii=False)


@mcp.tool()
def release_elastic_ip(
    allocation_id: str,
    region: str = "ap-northeast-2",
) -> str:
    """Elastic IP를 반납(해제)합니다. 더 이상 해당 IP를 소유하지 않습니다.

    Args:
        allocation_id: EIP 할당 ID (예: eipalloc-0abc1234)
        region: AWS 리전
    """
    ec2 = _ec2(region)
    ec2.release_address(AllocationId=allocation_id)
    return json.dumps({"status": "success", "message": f"{allocation_id} EIP 반납 완료"}, ensure_ascii=False)


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
    """EC2 인스턴스에 접속하기 위한 SSH 명령어를 생성합니다.

    Args:
        instance_id: 인스턴스 ID
        key_path: 로컬 pem 키 파일 경로 (예: ~/.ssh/my-key.pem)
        username: SSH 접속 유저명 (비워두면 AMI 기반으로 자동 추론)
        region: AWS 리전
    """
    ec2 = _ec2(region)
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    inst = resp["Reservations"][0]["Instances"][0]
    ip = inst.get("PublicIpAddress") or inst.get("PrivateIpAddress", "")
    ami_id = inst.get("ImageId", "")
    state = inst["State"]["Name"]

    if not username:
        # AMI 이름으로 유저 추론
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
        "note": "퍼블릭 IP가 없으면 VPN/Bastion을 통해 프라이빗 IP로 접속하세요." if not inst.get("PublicIpAddress") else "",
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def add_instance_tag(
    instance_id: str,
    key: str,
    value: str,
    region: str = "ap-northeast-2",
) -> str:
    """EC2 인스턴스에 태그를 추가하거나 값을 수정합니다.

    Args:
        instance_id: 인스턴스 ID
        key: 태그 키 (예: Name, Env, Owner)
        value: 태그 값 (예: my-server, production, changhyuk)
        region: AWS 리전
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
    """EC2 인스턴스 타입을 변경합니다. 실행 중이면 자동으로 중지 후 변경합니다.

    Args:
        instance_id: 인스턴스 ID
        new_instance_type: 변경할 인스턴스 타입 (예: t3.medium, c5.large)
        region: AWS 리전
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
        steps.append("인스턴스 중지 완료")

    ec2.modify_instance_attribute(
        InstanceId=instance_id,
        InstanceType={"Value": new_instance_type},
    )
    steps.append(f"타입 변경: {current_type} → {new_instance_type}")

    if current_state == "running":
        ec2.start_instances(InstanceIds=[instance_id])
        steps.append("인스턴스 재시작 완료")

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
    """S3 버킷 전체 목록과 생성일, 리전을 조회합니다."""
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
    """S3 버킷 내 파일(오브젝트) 목록을 조회합니다.

    Args:
        bucket: S3 버킷 이름
        prefix: 경로 필터 (예: logs/ 또는 2024/)
        max_keys: 최대 반환 개수 (기본 50)
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
    """새 S3 버킷을 생성합니다.

    Args:
        bucket_name: 생성할 버킷 이름 (전 세계 유일해야 함)
        region: AWS 리전
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
    """S3 버킷에서 특정 파일(오브젝트)을 삭제합니다.

    Args:
        bucket: S3 버킷 이름
        key: 삭제할 파일 경로 (예: logs/2024/app.log)
    """
    s3 = _s3()
    s3.delete_object(Bucket=bucket, Key=key)
    return json.dumps({"status": "success", "bucket": bucket, "key": key, "message": "삭제 완료"}, ensure_ascii=False)


@mcp.tool()
def get_s3_presigned_url(
    bucket: str,
    key: str,
    expires_in: int = 3600,
) -> str:
    """S3 오브젝트의 임시 다운로드 URL(Presigned URL)을 생성합니다.

    Args:
        bucket: S3 버킷 이름
        key: 파일 경로 (예: reports/result.pdf)
        expires_in: URL 유효 시간(초), 기본 3600초(1시간)
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
    """AWS Bedrock에서 사용 가능한 파운데이션 모델 목록을 조회합니다.

    Args:
        region: AWS 리전 (Bedrock은 us-east-1 또는 us-west-2 권장)
        provider: 공급자 필터 (예: Anthropic, Amazon, Meta, Mistral AI, 비워두면 전체)
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
    """AWS Bedrock을 통해 Claude 모델을 호출합니다.

    Args:
        prompt: 모델에게 보낼 메시지
        model_id: Bedrock 모델 ID (기본: Claude 3.5 Sonnet v2)
        max_tokens: 최대 응답 토큰 수
        region: AWS 리전
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
    """AWS Bedrock 모델을 raw JSON body로 직접 호출합니다. Claude 외 다른 모델(Titan, Llama 등) 사용 시 활용합니다.

    Args:
        model_id: Bedrock 모델 ID
        body: 모델별 요청 JSON 문자열
        region: AWS 리전
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
    """Bedrock Knowledge Base 목록을 조회합니다."""
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
    """Bedrock Knowledge Base에 질문하고 RAG 기반 답변을 받습니다.

    Args:
        knowledge_base_id: Knowledge Base ID
        query: 질문 내용
        model_id: 답변 생성에 사용할 모델 ID
        region: AWS 리전
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
