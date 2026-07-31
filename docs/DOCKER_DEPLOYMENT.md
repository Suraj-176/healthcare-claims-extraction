# Docker Deployment Guide
## Healthcare Claims Extraction Platform

---

## **📦 QUICK START**

### **Prerequisites:**
- Docker 20.10+ installed
- Docker Compose 2.0+ installed
- 4GB RAM minimum, 8GB recommended
- 20GB disk space

### **1. Clone & Configure:**

```bash
# Clone repository
git clone <repository-url>
cd HealthInsurance_Claims_Extraction

# Copy environment template
cp .env.example .env

# Edit .env and add your API keys
nano .env  # or use your preferred editor
```

### **2. Build & Start:**

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f web

# Check status
docker-compose ps
```

### **3. Access Application:**

- **Web UI:** http://localhost:5000
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379
- **pgAdmin (optional):** http://localhost:5050

---

## **🏗️ ARCHITECTURE**

### **Services:**

| Service | Purpose | Port | Resources |
|---------|---------|------|-----------|
| **web** | Flask application | 5000 | 2 CPU, 4GB RAM |
| **db** | PostgreSQL database | 5432 | 1 CPU, 1GB RAM |
| **redis** | Cache & job queue | 6379 | 0.5 CPU, 512MB |
| **worker** | Background processing | - | 1 CPU, 2GB RAM |
| **pgadmin** | DB management (optional) | 5050 | - |

### **Volumes:**

- `postgres_data` - Database persistence
- `redis_data` - Redis persistence
- `./data` - Application data (mounted)
- `./logs` - Application logs (mounted)

---

## **⚙️ CONFIGURATION**

### **Required Environment Variables:**

```bash
# Azure OpenAI (Primary)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-key-here
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# Database (auto-configured in docker-compose)
DATABASE_URL=postgresql://claims_user:claims_password@db:5432/claims_db

# Flask
SECRET_KEY=generate-a-random-secret-key
```

### **Optional Environment Variables:**

```bash
# Alternative LLM providers
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...

# Redis
REDIS_URL=redis://redis:6379/0

# Processing
MAX_WORKERS=4
PROCESSING_TIMEOUT=120
LLM_CONFIDENCE_THRESHOLD=50
```

---

## **🚀 DEPLOYMENT SCENARIOS**

### **Development Mode:**

```bash
# Use SQLite, single worker
docker-compose up web

# Or with hot reload
docker-compose run --rm web flask run --host=0.0.0.0 --debug
```

### **Production Mode:**

```bash
# Full stack with PostgreSQL, Redis, workers
docker-compose up -d

# Scale workers
docker-compose up -d --scale worker=4
```

### **Debug Mode:**

```bash
# Start with pgAdmin for database inspection
docker-compose --profile debug up -d

# Access pgAdmin: http://localhost:5050
# Email: admin@example.com
# Password: admin
```

---

## **📊 MONITORING & LOGS**

### **View Logs:**

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web
docker-compose logs -f worker

# Last 100 lines
docker-compose logs --tail=100 web
```

### **Health Checks:**

```bash
# Check all services
docker-compose ps

# Test web health
curl http://localhost:5000/api/stats

# Check database connection
docker-compose exec db psql -U claims_user -d claims_db -c "SELECT 1;"
```

### **Resource Usage:**

```bash
# Monitor container stats
docker stats

# Specific service
docker stats claims-extraction-web
```

---

## **🔧 MAINTENANCE**

### **Database Management:**

```bash
# Backup database
docker-compose exec db pg_dump -U claims_user claims_db > backup.sql

# Restore database
docker-compose exec -T db psql -U claims_user claims_db < backup.sql

# Clear all data (reset)
docker-compose down -v
docker-compose up -d
```

### **Update Application:**

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### **Clean Up:**

```bash
# Stop all services
docker-compose down

# Remove volumes (CAUTION: deletes data)
docker-compose down -v

# Remove images
docker rmi $(docker images -q healthinsurance_claims_extraction_*)
```

---

## **🐛 TROUBLESHOOTING**

### **Service Won't Start:**

```bash
# Check logs for errors
docker-compose logs web

# Verify environment variables
docker-compose config

# Restart specific service
docker-compose restart web
```

### **Database Connection Issues:**

```bash
# Verify database is running
docker-compose ps db

# Check database logs
docker-compose logs db

# Test connection
docker-compose exec web python -c "from src.database.db_manager import DatabaseManager; print(DatabaseManager().get_statistics())"
```

### **Out of Memory:**

```bash
# Check resource usage
docker stats

# Increase limits in docker-compose.yml:
deploy:
  resources:
    limits:
      memory: 8G  # Increase from 4G
```

### **Port Already in Use:**

```bash
# Find process using port 5000
lsof -i :5000  # macOS/Linux
netstat -ano | findstr :5000  # Windows

# Change port in docker-compose.yml:
ports:
  - "8000:5000"  # Map to different external port
```

---

## **🔐 SECURITY BEST PRACTICES**

### **1. Environment Variables:**

```bash
# Never commit .env to version control
echo ".env" >> .gitignore

# Use secrets management in production
docker secret create azure_key /path/to/key/file
```

### **2. Database Security:**

```bash
# Change default passwords in docker-compose.yml
POSTGRES_PASSWORD: use_strong_password_here

# Restrict database access
# Remove port mapping in production:
# ports:
#   - "5432:5432"
```

### **3. Network Security:**

```bash
# Use internal network for services
# Only expose web service externally

# Add reverse proxy (nginx) in front
# Handle SSL/TLS termination
```

### **4. Update Dependencies:**

```bash
# Keep base images updated
docker-compose pull
docker-compose up -d
```

---

## **📈 SCALING**

### **Horizontal Scaling:**

```bash
# Scale workers
docker-compose up -d --scale worker=10

# Use load balancer for web services
docker-compose up -d --scale web=3
```

### **Kubernetes Deployment:**

```yaml
# Example k8s deployment (create separate manifests)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: claims-extraction
spec:
  replicas: 3
  selector:
    matchLabels:
      app: claims-extraction
  template:
    metadata:
      labels:
        app: claims-extraction
    spec:
      containers:
      - name: web
        image: claims-extraction:latest
        ports:
        - containerPort: 5000
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
```

---

## **🧪 TESTING IN DOCKER**

### **Run Tests:**

```bash
# Run all tests
docker-compose run --rm web pytest tests/

# Run specific test
docker-compose run --rm web pytest tests/test_pipeline_skeleton.py

# Run with coverage
docker-compose run --rm web pytest --cov=src tests/
```

### **Benchmark:**

```bash
# Run benchmark script
docker-compose run --rm web python benchmark.py

# Check results
ls -lh 05_Benchmark.xlsx
```

---

## **📦 PRODUCTION DEPLOYMENT**

### **AWS ECS:**

```bash
# Build and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker build -t claims-extraction .
docker tag claims-extraction:latest <account>.dkr.ecr.us-east-1.amazonaws.com/claims-extraction:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/claims-extraction:latest

# Deploy ECS task
aws ecs update-service --cluster prod-cluster --service claims-extraction --force-new-deployment
```

### **Google Cloud Run:**

```bash
# Build and deploy
gcloud builds submit --tag gcr.io/<project-id>/claims-extraction
gcloud run deploy claims-extraction --image gcr.io/<project-id>/claims-extraction --platform managed
```

### **Azure Container Instances:**

```bash
# Build and push to ACR
az acr build --registry <registry-name> --image claims-extraction:latest .

# Deploy to ACI
az container create --resource-group prod-rg --name claims-extraction --image <registry-name>.azurecr.io/claims-extraction:latest --cpu 2 --memory 4
```

---

## **✅ PRODUCTION CHECKLIST**

- [ ] Environment variables configured with production values
- [ ] Secret keys rotated and stored securely
- [ ] Database passwords changed from defaults
- [ ] SSL/TLS certificates configured
- [ ] Reverse proxy (nginx/Traefik) set up
- [ ] Monitoring and alerting configured
- [ ] Backup strategy implemented
- [ ] Log aggregation configured
- [ ] Resource limits tuned for production
- [ ] Health checks validated
- [ ] Auto-scaling policies configured
- [ ] Disaster recovery plan documented
- [ ] Security audit completed

---

## **📞 SUPPORT**

For deployment issues:
1. Check logs: `docker-compose logs -f`
2. Verify configuration: `docker-compose config`
3. Test services individually
4. Review this guide's troubleshooting section

---

**Last Updated:** 2026-07-31  
**Docker Version:** 20.10+  
**Docker Compose Version:** 2.0+
