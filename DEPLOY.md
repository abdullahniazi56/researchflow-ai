# Deploying ResearchFlow AI on Oracle Cloud (Always Free)

The whole stack runs on one free ARM virtual machine with Docker Compose.
Caddy is the only public service: it serves the site over HTTPS and forwards
`/api` to the backend. Postgres, Qdrant and the backend are private.

```
Internet ──HTTPS──▶ Caddy ──▶ frontend (nginx, React build)
                       └─/api─▶ backend (FastAPI + MCP + models)
                                    ├─▶ postgres
                                    └─▶ qdrant
```

## 1. Create the server

1. Sign up at https://www.oracle.com/cloud/free/ (the card is used for verification).
   Pick a **home region** close to you; it can't be changed later.
2. Console → **Compute → Instances → Create instance**
   - **Image:** Canonical Ubuntu 24.04
   - **Shape:** Ampere → `VM.Standard.A1.Flex`, **2 OCPU, 12 GB RAM** (Always Free limit)
   - **Networking:** create a new VCN with a **public subnet**, and assign a **public IPv4 address**
   - **SSH keys:** "Generate a key pair for me" and **download the private key**
   - Boot volume: 50 GB is enough
   - If you see "Out of capacity", try another availability domain or try again later.
3. Note the instance's **public IP address**.

## 2. Open ports 80 and 443

**In Oracle's firewall:** Instance → Subnet → Security List → *Add Ingress Rules*:

| Source CIDR | Protocol | Destination port |
|---|---|---|
| 0.0.0.0/0 | TCP | 80 |
| 0.0.0.0/0 | TCP | 443 |

**On the server** (Oracle's Ubuntu image also blocks ports with iptables), after step 4:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Get a free domain name

HTTPS needs a domain. Free option: https://www.duckdns.org (sign in with GitHub),
create a subdomain such as `researchflow`, and set its IP to the server's public IP.
Your site will be `https://researchflow.duckdns.org`.

## 4. Connect with SSH

Windows (PowerShell), with the downloaded key:

```powershell
# Once: SSH refuses keys that other users can read
icacls C:\path\to\ssh-key.key /inheritance:r
icacls C:\path\to\ssh-key.key /grant:r "$($env:USERNAME):R"

ssh -i C:\path\to\ssh-key.key ubuntu@<PUBLIC_IP>
```

## 5. Install Docker and get the code

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit        # log out and SSH in again so the group change applies

git clone https://github.com/<your-username>/researchflow-ai.git
cd researchflow-ai
cp .env.example .env
nano .env
```

In `.env` set at least:

```
DOMAIN=researchflow.duckdns.org
POSTGRES_PASSWORD=<a long random password>
GOOGLE_API_KEY=...
MISTRAL_API_KEY=...
TAVILY_API_KEY=...
LLM_PROVIDER=gemini
```

## 6. Start everything

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The first build downloads PyTorch and the models, so it takes a while
(roughly 10–20 minutes on the free VM). Then:

```bash
# Index the sample PDFs (Nike, Puma, Loro Piana)
docker compose -f docker-compose.prod.yml exec backend python -m eval.run_eval --ingest

# Follow the logs
docker compose -f docker-compose.prod.yml logs -f backend caddy
```

Open `https://<your-domain>`. Caddy gets the HTTPS certificate on the first request.

## Updating

```bash
cd researchflow-ai
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## Troubleshooting

| Symptom | Check |
|---|---|
| Site doesn't load at all | Ports 80/443 open in **both** the Security List and iptables (step 2); DuckDNS points to the right IP |
| HTTPS certificate error | `docker compose -f docker-compose.prod.yml logs caddy`; the domain must resolve to the server before Caddy can get a certificate |
| "Server offline" in the app | `docker compose -f docker-compose.prod.yml logs backend` |
| Answers fail with "usage limit" | The LLM quota is used up; switch `LLM_PROVIDER` in `.env` and run `docker compose -f docker-compose.prod.yml up -d` |
