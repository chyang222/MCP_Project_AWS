# AWS MCP Server

An MCP server that lets you control AWS resources directly from Claude Desktop or Claude Code.

## Available Tools

### Security Groups
| Tool | Description |
|------|-------------|
| `list_security_groups` | List all security groups with inbound/outbound rules |
| `get_my_public_ip` | Get the current public IP address |
| `add_my_ip_to_security_group` | Add current IP to a specified security group |
| `remove_ip_from_security_group` | Remove a specific CIDR rule from a security group |
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

## Installation & Setup (Windows)

### Prerequisites

- [Python 3.10+](https://www.python.org/downloads/) (check **"Add Python to PATH"** during install)
- [Git](https://git-scm.com/download/win)

### 1. Clone the repository

Open Command Prompt or PowerShell and run:

```cmd
git clone https://github.com/chyang222/MCP_Project_AWS.git
cd MCP_Project_AWS
```

### 2. Configure environment variables

```cmd
copy .env.example .env
```

Open `.env` in a text editor and fill in your AWS credentials:

```env
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=ap-northeast-2
```

### 3. Install dependencies

```cmd
pip install -r requirements.txt
```

### 4. Test the server

```cmd
python server.py
```

You should see `MCP server running...` if everything is working.

---

## Claude Desktop Integration

Config file path (Windows):

```
%APPDATA%\Claude\claude_desktop_config.json
```

> Paste `%APPDATA%\Claude\` into the Explorer address bar to navigate there directly.

Add the following to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aws": {
      "command": "python",
      "args": ["C:\\Users\\<your-username>\\MCP_Project_AWS\\server.py"],
      "env": {
        "AWS_ACCESS_KEY_ID": "your_access_key",
        "AWS_SECRET_ACCESS_KEY": "your_secret_key",
        "AWS_DEFAULT_REGION": "ap-northeast-2"
      }
    }
  }
}
```

> Replace `C:\\Users\\<your-username>\\MCP_Project_AWS\\` with your actual clone path.  
> Use double backslashes (`\\`) in JSON paths.

---

## Claude Code Integration

```cmd
claude mcp add aws python C:\Users\<your-username>\MCP_Project_AWS\server.py
```

Or add directly to `.claude\settings.json`:

```json
{
  "mcpServers": {
    "aws": {
      "command": "python",
      "args": ["C:\\Users\\<your-username>\\MCP_Project_AWS\\server.py"]
    }
  }
}
```

---

## Usage Examples

```
Show me all security groups
Add my IP to security group sg-0abc1234 on port 22
List all running EC2 instances
Create a t3.micro instance
Stop instance i-0abc1234
```

---

## Troubleshooting

**`python` not found**
- Make sure "Add Python to PATH" was checked during installation
- Close and reopen CMD, then verify with `python --version`

**`pip install` errors**
```cmd
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**AWS authentication errors**
- Verify the key values in your `.env` file are correct
- Confirm the IAM user has the required permissions
