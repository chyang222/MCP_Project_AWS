# AWS MCP Server

Claude Desktop / Claude Code에서 AWS 리소스를 직접 제어할 수 있는 MCP 서버입니다.

## 제공 도구 목록

### 보안그룹
| Tool | 설명 |
|------|------|
| `list_security_groups` | 전체 보안그룹 목록 + 인바운드/아웃바운드 규칙 조회 |
| `get_my_public_ip` | 현재 공인 IP 확인 |
| `add_my_ip_to_security_group` | 현재 IP를 지정 보안그룹에 자동 추가 |
| `remove_ip_from_security_group` | 보안그룹에서 특정 CIDR 규칙 제거 |
| `create_security_group` | 새 보안그룹 생성 |

### EC2 인스턴스
| Tool | 설명 |
|------|------|
| `list_ec2_instances` | 인스턴스 목록 + 상태/IP/타입 조회 |
| `get_instance_details` | 특정 인스턴스 상세 정보 |
| `start_ec2_instance` | 인스턴스 시작 |
| `stop_ec2_instance` | 인스턴스 중지 |
| `reboot_ec2_instance` | 인스턴스 재부팅 |
| `create_ec2_instance` | 새 인스턴스 생성 |
| `terminate_ec2_instance` | 인스턴스 영구 삭제 |
| `get_instance_console_output` | 부팅 로그(콘솔 출력) 조회 |

### Elastic IP
| Tool | 설명 |
|------|------|
| `list_elastic_ips` | 할당된 EIP 목록 + 연결 인스턴스 정보 |
| `allocate_elastic_ip` | 새 EIP 할당 |
| `associate_elastic_ip` | EIP를 인스턴스에 연결 |
| `disassociate_elastic_ip` | EIP 연결 해제 |
| `release_elastic_ip` | EIP 반납 |

### 편의 기능
| Tool | 설명 |
|------|------|
| `get_ssh_command` | SSH 접속 명령어 자동 생성 (AMI 기반 username 추론) |
| `add_instance_tag` | 인스턴스 태그 추가/수정 |
| `change_instance_type` | 인스턴스 타입 변경 (실행 중이면 자동 중지 후 변경) |

### S3
| Tool | 설명 |
|------|------|
| `list_s3_buckets` | 전체 버킷 목록 + 리전 |
| `list_s3_objects` | 버킷 내 파일 목록 (prefix 필터 지원) |
| `create_s3_bucket` | 새 버킷 생성 |
| `delete_s3_object` | 버킷 내 파일 삭제 |
| `get_s3_presigned_url` | 임시 다운로드 URL 생성 |

### Bedrock AI
| Tool | 설명 |
|------|------|
| `list_bedrock_models` | 사용 가능한 파운데이션 모델 목록 (공급자 필터 지원) |
| `invoke_bedrock_claude` | Claude 모델 호출 (기본: Claude 3.5 Sonnet v2) |
| `invoke_bedrock_model_raw` | 임의 Bedrock 모델 raw JSON 호출 |
| `list_bedrock_knowledge_bases` | Knowledge Base 목록 조회 |
| `query_bedrock_knowledge_base` | Knowledge Base RAG 질의응답 |

### 인프라 정보
| Tool | 설명 |
|------|------|
| `list_key_pairs` | 사용 가능한 키페어 목록 |
| `list_vpcs` | VPC + 서브넷 목록 |
| `list_available_amis` | 최신 공식 AMI 목록 (Amazon Linux / Ubuntu / Windows) |

## 설치 및 실행

```bash
# 1. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY 입력

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 서버 실행 테스트
python server.py
```

## Claude Desktop 연동 설정

`~/.config/claude/claude_desktop_config.json` (Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "aws": {
      "command": "python",
      "args": ["/home/dev/project/mcp/aws_mcp/server.py"],
      "env": {
        "AWS_ACCESS_KEY_ID": "your_key",
        "AWS_SECRET_ACCESS_KEY": "your_secret",
        "AWS_DEFAULT_REGION": "ap-northeast-2"
      }
    }
  }
}
```

## Claude Code 연동 설정

```bash
claude mcp add aws python3.13 /home/dev/project/mcp/aws_mcp/server.py
```

또는 `.claude/settings.json`에 추가:

```json
{
  "mcpServers": {
    "aws": {
      "command": "python3.13",
      "args": ["/home/dev/project/mcp/aws_mcp/server.py"]
    }
  }
}
```

## 사용 예시

```
현재 보안그룹 목록 보여줘
내 IP를 sg-0abc1234 보안그룹 22번 포트에 추가해줘
실행 중인 EC2 인스턴스 목록 보여줘
t3.micro 인스턴스 하나 만들어줘
i-0abc1234 인스턴스 중지해줘
```
