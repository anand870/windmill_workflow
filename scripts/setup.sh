#!/bin/bash

# Windmill Development Environment Setup Script
# This script initializes the data directories and starts the environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Windmill Development Environment Setup${NC}\n"

# Check if Docker and Docker Compose are installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker and Docker Compose are installed${NC}\n"

# Create data directories
echo -e "${YELLOW}📁 Creating data directories...${NC}"
mkdir -p data/postgres
mkdir -p data/redis
mkdir -p data/windmill

echo -e "${GREEN}✓ Data directories created${NC}\n"

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  .env file not found${NC}"
    echo -e "${YELLOW}   Creating default .env file...${NC}"
    cp .env.example .env 2>/dev/null || echo "   (No .env.example found, using defaults)"
    echo -e "${YELLOW}   Please review and update .env if needed${NC}\n"
fi

# Pull latest images
echo -e "${YELLOW}🐳 Pulling latest Docker images...${NC}"
docker-compose pull

echo -e "${GREEN}✓ Images pulled${NC}\n"

# Start services
echo -e "${YELLOW}▶️  Starting services...${NC}"
docker-compose up -d

echo -e "${GREEN}✓ Services started${NC}\n"

# Wait for services to be ready
echo -e "${YELLOW}⏳ Waiting for services to be healthy...${NC}"
sleep 5

# Check service health
for i in {1..30}; do
    if docker-compose exec -T windmill curl -f http://localhost:8000/api/version &> /dev/null; then
        echo -e "${GREEN}✓ Windmill is ready${NC}\n"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Windmill did not start within timeout${NC}"
        echo -e "${YELLOW}   Check logs with: docker-compose logs windmill${NC}"
        exit 1
    fi
    echo -n "."
    sleep 1
done

# Show summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✨ Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo "Access Windmill at: ${GREEN}http://localhost:8000${NC}"
echo -e "Database: ${GREEN}postgres://localhost:5432/windmill${NC}"
echo -e "Redis: ${GREEN}redis://localhost:6379${NC}\n"

echo "Useful commands:"
echo "  View logs:       ${YELLOW}docker-compose logs -f${NC}"
echo "  Stop services:   ${YELLOW}docker-compose down${NC}"
echo "  Restart services:${YELLOW}docker-compose restart${NC}"
echo "  View status:     ${YELLOW}docker-compose ps${NC}\n"

echo -e "${YELLOW}📖 Next steps:${NC}"
echo "  1. Open http://localhost:8000 in your browser"
echo "  2. Create your admin account on first login"
echo "  3. Start creating flows and scripts!"
