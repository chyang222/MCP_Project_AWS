# claude-aws-mcp

[![PyPI version](https://img.shields.io/pypi/v/claude-aws-mcp)](https://pypi.org/project/claude-aws-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/claude-aws-mcp)](https://pypi.org/project/claude-aws-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP server that lets you control AWS resources directly from **Claude Desktop** or **Claude Code** using natural language.

---

## Installation

```cmd
pip install claude-aws-mcp
```

> Requires Python 3.10 or higher.

---

## Quick Start (Windows)

### Prerequisites

- [Python 3.10+](https://www.python.org/downloads/) — check **"Add Python to PATH"** during install
- [Git](https://git-scm.com/download/win)

### 1. Install the package

```cmd
pip install claude-aws-mcp
```

### 2. Create a `.env` file

Create a file named `.env` in your working directory:

```env
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=ap-northeast-2
```

### 3. Run the server

```cmd
aws-mcp
```

---

## Claude Desktop Integration

Config file location:

| OS | Path |
|----|------|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Mac | `~/Library/Application Support/Claude/claude_desktop_config.json` |

> On Windows, paste `%APPDATA%\Claude\` into the Explorer address bar to navigate there directly.

Add the following to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aws": {
      "command": "aws-mcp",
      "env": {
        "AWS_ACCESS_KEY_ID": "your_access_key",
        "AWS_SECRET_ACCESS_KEY": "your_secret_key",
        "AWS_DEFAULT_REGION": "ap-northeast-2"
      }
    }
  }
}
```

Restart Claude Desktop — the AWS tools will appear automatically.

---

## Claude Code Integration

```cmd
claude mcp add aws aws-mcp
```

Or add directly to `.claude\settings.json`:

```json
{
  "mcpServers": {
    "aws": {
      "command": "aws-mcp"
    }
  }
}
```

---

## Available Tools

### Security Groups
| Tool | Description |
|------|-------------|
| `list_security_groups` | List all security groups with inbound/outbound rules |
| `get_my_public_ip` | Get the current public IP address |
| `add_my_ip_to_security_group` | Add current IP to a specified security group |
| `remove_ip_from_security_group` | Remove a specific CIDR rule from a security group (supports port ranges, e.g. `0-65535`) |
| `create_security_group` | Create a new security group |

### EC2 Instances
| Tool | Description |
|------|-------------|
| `list_ec2_instances` | List instances with state, IP, and type |
| `get_instance_details` | Get detailed info for a specific instance |
| `start_ec2_instance` | Start an instance |
| `stop_ec2_instance` | Stop an instance |
| `reboot_ec2_instance` | Reboot an instance |
| `create_ec2_instance` | Create a new instance |
| `terminate_ec2_instance` | Permanently delete an instance |
| `get_instance_console_output` | Get boot log (console output) |

### Elastic IP
| Tool | Description |
|------|-------------|
| `list_elastic_ips` | List allocated EIPs with associated instance info |
| `allocate_elastic_ip` | Allocate a new EIP |
| `associate_elastic_ip` | Associate an EIP with an instance |
| `disassociate_elastic_ip` | Disassociate an EIP |
| `release_elastic_ip` | Release an EIP |

### Utilities
| Tool | Description |
|------|-------------|
| `get_ssh_command` | Generate SSH command (auto-detects username from AMI) |
| `add_instance_tag` | Add or update instance tags |
| `change_instance_type` | Change instance type (auto stops if running) |

### S3
| Tool | Description |
|------|-------------|
| `list_s3_buckets` | List all buckets with region |
| `list_s3_objects` | List objects in a bucket (supports prefix filter) |
| `create_s3_bucket` | Create a new bucket |
| `delete_s3_object` | Delete a file from a bucket |
| `get_s3_presigned_url` | Generate a temporary download URL |

### Bedrock AI
| Tool | Description |
|------|-------------|
| `list_bedrock_models` | List available foundation models (supports provider filter) |
| `invoke_bedrock_claude` | Invoke Claude model (default: Claude 3.5 Sonnet v2) |
| `invoke_bedrock_model_raw` | Invoke any Bedrock model with raw JSON |
| `list_bedrock_knowledge_bases` | List Knowledge Bases |
| `query_bedrock_knowledge_base` | RAG query against a Knowledge Base |

### Infrastructure Info
| Tool | Description |
|------|-------------|
| `list_key_pairs` | List available key pairs |
| `list_vpcs` | List VPCs and subnets |
| `list_available_amis` | List latest official AMIs (Amazon Linux / Ubuntu / Windows) |

---

## Example Prompts

Once connected to Claude, just type naturally:

```
Show me all security groups
Add my current IP to sg-0abc1234 on port 22
Remove 0.0.0.0/0 from sg-0abc1234 on port range 0-65535
List all running EC2 instances
Stop instance i-0abc1234
Create a t3.micro instance
List all S3 buckets
Generate a presigned URL for my-bucket/report.pdf
Ask Claude via Bedrock: "Summarize the AWS Well-Architected Framework"
```

---

## IAM Permissions

Your AWS IAM user needs the following policies:

| Service | Recommended Policy |
|---|---|
| EC2 / Security Groups | `AmazonEC2FullAccess` |
| S3 | `AmazonS3FullAccess` |
| Bedrock | `AmazonBedrockFullAccess` |

---

## Troubleshooting

**`aws-mcp` command not found after install**
- Close and reopen CMD, then retry
- Or run: `python -m aws_mcp.server`

**`pip` errors**
```cmd
python -m pip install --upgrade pip
pip install claude-aws-mcp
```

**AWS authentication errors**
- Check that your `.env` values are correct
- Confirm the IAM user has the required permissions

**Python not found**
- Reinstall Python and make sure **"Add Python to PATH"** is checked
- Verify with: `python --version`

---

## Links

- **PyPI:** https://pypi.org/project/claude-aws-mcp/
- **GitHub:** https://github.com/chyang222/MCP_Project_AWS
