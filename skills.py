"""Canonical skill taxonomy, learning-time estimates, courses and job role templates.

Everything in the graph uses these exact names, so no entity resolution is needed anywhere.
Levels are 1 (working knowledge), 2 (independent / production), 3 (expert / certified / at scale).
For language skills the levels map to JLPT N3 / N2 / N1 and conversational / business / fluent.
"""

# skill -> estimated days to reach level 2 from zero (hackathon-grade estimates)
LEARN_DAYS = {
    # containers & platform
    "Kubernetes": 30, "Docker": 5, "Helm": 5, "OpenShift": 14, "OpenStack": 21, "Service Mesh (Istio)": 10,
    # cloud & IaC
    "AWS": 21, "GCP": 21, "Azure": 21, "Terraform": 10, "Ansible": 10,
    # OS / infrastructure
    "Linux": 21, "Bare-metal Provisioning": 30, "Networking (L2/L3)": 30, "Storage (Ceph/SAN)": 21,
    "Virtualization (VMware/KVM)": 14,
    # languages
    "Python": 30, "Bash": 10, "Go": 30, "Java": 45, "TypeScript": 30, "SQL": 10,
    # CI/CD & GitOps
    "Git": 3, "CI/CD (GitLab CI/GitHub Actions)": 7, "GitOps (ArgoCD/Flux)": 5,
    # observability & SRE
    "Prometheus/Grafana": 7, "Logging (ELK/Loki)": 7, "Datadog": 5, "Incident Management/RCA": 7,
    "SRE Practices (SLOs/On-call)": 14,
    # security
    "Cloud Security/IAM": 14, "Secrets Management (Vault)": 5,
    # data
    "PostgreSQL": 14, "Kafka": 14, "Redis": 5, "Spark": 21,
    # telecom
    "Open RAN/5G": 45, "Telecom Core Networks": 45,
    # leadership & ways of working
    "Team Leadership": 60, "Mentoring": 30, "Technical Documentation": 5, "Agile/Scrum": 3,
    # human languages
    "English": 180, "Japanese": 365,
}

CANONICAL_SKILLS = list(LEARN_DAYS)

LEVEL_LABELS = {
    "Japanese": {1: "N3", 2: "N2", 3: "N1"},
    "English": {1: "conversational", 2: "business", 3: "fluent"},
}

COURSE_PROVIDERS = {
    "Kubernetes": "KodeKloud CKA", "Docker": "Docker Mastery (Udemy)", "Helm": "KodeKloud", "Terraform": "HashiCorp Learn",
    "AWS": "AWS Skill Builder (SAA)", "GCP": "Google Cloud Skills Boost", "Azure": "Microsoft Learn (AZ-104)",
    "Go": "Go by Example + Tour of Go", "Prometheus/Grafana": "Prometheus Certified Associate prep",
    "CI/CD (GitLab CI/GitHub Actions)": "GitLab CI Masterclass", "GitOps (ArgoCD/Flux)": "Codefresh GitOps Fundamentals",
    "Japanese": "JLPT N2 prep (Japan Foundation / Shin Kanzen Master)", "English": "Business English (Coursera)",
    "Team Leadership": "Engineering Management (Coursera)",
}


def course_for(skill: str) -> dict:
    return {
        "id": f"course:{skill}",
        "name": COURSE_PROVIDERS.get(skill, f"{skill} Fundamentals (Udemy)"),
        "skill": skill,
        "days": LEARN_DAYS[skill],
        "to_level": 2,
    }


COURSES = [course_for(s) for s in CANONICAL_SKILLS]

# Fictional-but-plausible Tokyo employers. The demo corpus is synthetic and labelled as such in the UI.
COMPANIES = [
    ("Sakura Cloud K.K.", "Shinagawa"), ("Fuji Telecom", "Minato"), ("Hikari Networks", "Chiyoda"),
    ("Tsukiji Fintech", "Chuo"), ("Kanda Robotics", "Chiyoda"), ("Shibuya Pay", "Shibuya"),
    ("Nihonbashi Capital Tech", "Chuo"), ("Yotsuya Mobility", "Shinjuku"), ("Akiba Semiconductor Cloud", "Chiyoda"),
    ("Minato Digital", "Minato"), ("Ebisu Games Infra", "Shibuya"), ("Toyosu Data Systems", "Koto"),
    ("Ginza Retail Tech", "Chuo"), ("Marunouchi Bank Digital", "Chiyoda"), ("Odaiba Media Cloud", "Koto"),
    ("Kawasaki Industrial IoT", "Kawasaki"), ("Yokohama Port Logistics Tech", "Yokohama"), ("Shinjuku HR Tech", "Shinjuku"),
    ("Ueno MedTech", "Taito"), ("Roppongi AdTech", "Minato"), ("Harajuku Commerce", "Shibuya"), ("Meguro SaaS", "Meguro"),
    ("Chiyoda GovTech", "Chiyoda"), ("Tama Energy Grid", "Tama"), ("Kichijoji EdTech", "Musashino"),
]

# Role templates. core: always required. optional: (skill, level, probability). jp: probability the
# role requires Japanese N2 (level 2). Counts sum to 300.
# Each core/optional entry: (skill, level, mandatory)
ROLE_TEMPLATES = [
    {
        "title": "Platform Engineer (Kubernetes)", "count": 45, "jp": 0.35,
        "core": [("Kubernetes", 3, True), ("Linux", 2, False), ("Helm", 2, False)],
        "optional": [("Terraform", 2, 0.7), ("AWS", 2, 0.6), ("GCP", 2, 0.25), ("Go", 2, 0.5), ("Python", 2, 0.5),
                     ("CI/CD (GitLab CI/GitHub Actions)", 2, 0.7), ("GitOps (ArgoCD/Flux)", 2, 0.5),
                     ("Prometheus/Grafana", 2, 0.6), ("Docker", 2, 0.6), ("Service Mesh (Istio)", 1, 0.3)],
    },
    {
        "title": "Site Reliability Engineer", "count": 45, "jp": 0.35,
        "core": [("Kubernetes", 2, False), ("Linux", 2, False), ("Prometheus/Grafana", 2, True),
                 ("SRE Practices (SLOs/On-call)", 2, False), ("Incident Management/RCA", 2, False)],
        "optional": [("Python", 2, 0.6), ("Go", 2, 0.5), ("AWS", 2, 0.6), ("Terraform", 2, 0.6),
                     ("CI/CD (GitLab CI/GitHub Actions)", 2, 0.5), ("Logging (ELK/Loki)", 2, 0.5), ("Datadog", 1, 0.3),
                     ("Bash", 2, 0.5)],
    },
    {
        "title": "Cloud Infrastructure Engineer", "count": 45, "jp": 0.4,
        "core": [("AWS", 2, True), ("Terraform", 2, True), ("Linux", 2, False)],
        "optional": [("Kubernetes", 2, 0.6), ("Ansible", 2, 0.5), ("Python", 2, 0.5), ("Networking (L2/L3)", 2, 0.5),
                     ("Cloud Security/IAM", 2, 0.5), ("Bash", 2, 0.4), ("CI/CD (GitLab CI/GitHub Actions)", 2, 0.4),
                     ("Azure", 1, 0.2), ("GCP", 1, 0.2)],
    },
    {
        "title": "DevOps Engineer", "count": 40, "jp": 0.45,
        "core": [("Docker", 2, False), ("Kubernetes", 2, False), ("CI/CD (GitLab CI/GitHub Actions)", 2, True), ("Git", 2, False)],
        "optional": [("Terraform", 2, 0.6), ("AWS", 2, 0.6), ("Ansible", 2, 0.4), ("Python", 2, 0.5), ("Bash", 2, 0.5),
                     ("GitOps (ArgoCD/Flux)", 2, 0.4), ("Prometheus/Grafana", 2, 0.4)],
    },
    {
        "title": "Telecom Cloud Engineer (Open RAN / 5G Core)", "count": 30, "jp": 0.3,
        "core": [("Kubernetes", 2, False), ("Linux", 3, False), ("Networking (L2/L3)", 3, False), ("OpenStack", 2, False),
                 ("Open RAN/5G", 2, True)],
        "optional": [("Ansible", 2, 0.7), ("Python", 2, 0.6), ("Bare-metal Provisioning", 2, 0.6), ("Bash", 2, 0.5),
                     ("Telecom Core Networks", 2, 0.4), ("Helm", 2, 0.4)],
    },
    {
        "title": "Data Center Infrastructure Engineer", "count": 25, "jp": 0.5,
        "core": [("Linux", 3, False), ("Bare-metal Provisioning", 3, True), ("Networking (L2/L3)", 2, False)],
        "optional": [("Ansible", 2, 0.7), ("Virtualization (VMware/KVM)", 2, 0.5), ("Storage (Ceph/SAN)", 2, 0.5),
                     ("Python", 2, 0.4), ("Bash", 2, 0.6), ("OpenStack", 2, 0.3)],
    },
    {
        "title": "Backend Engineer (Go/Python)", "count": 25, "jp": 0.4,
        "core": [("Go", 2, True), ("PostgreSQL", 2, False), ("Docker", 2, False), ("Git", 2, False)],
        "optional": [("Python", 2, 0.5), ("Kubernetes", 2, 0.5), ("AWS", 2, 0.6), ("Redis", 1, 0.4), ("Kafka", 2, 0.3),
                     ("CI/CD (GitLab CI/GitHub Actions)", 2, 0.5), ("TypeScript", 2, 0.3)],
    },
    {
        "title": "Cloud Security Engineer", "count": 15, "jp": 0.4,
        "core": [("Cloud Security/IAM", 2, True), ("AWS", 2, False), ("Linux", 2, False)],
        "optional": [("Kubernetes", 2, 0.5), ("Terraform", 2, 0.6), ("Secrets Management (Vault)", 2, 0.5), ("Python", 2, 0.5)],
    },
    {
        "title": "Data Platform Engineer", "count": 15, "jp": 0.35,
        "core": [("Python", 2, False), ("Spark", 2, True), ("Kafka", 2, False), ("SQL", 2, False)],
        "optional": [("Kubernetes", 2, 0.5), ("AWS", 2, 0.6), ("Terraform", 2, 0.3), ("PostgreSQL", 2, 0.4)],
    },
    {
        "title": "Infrastructure Team Lead", "count": 15, "jp": 0.6,
        "core": [("Team Leadership", 2, True), ("Kubernetes", 2, False), ("Linux", 2, False), ("Mentoring", 2, False)],
        "optional": [("AWS", 2, 0.5), ("Terraform", 2, 0.4), ("Agile/Scrum", 2, 0.6), ("Incident Management/RCA", 2, 0.5),
                     ("Ansible", 2, 0.3)],
    },
]

SENIORITY_PREFIXES = ["", "", "Senior ", "Senior ", "Lead "]

assert sum(r["count"] for r in ROLE_TEMPLATES) == 300
for _r in ROLE_TEMPLATES:
    for _s, _, *_ in _r["core"] + _r["optional"]:
        assert _s in LEARN_DAYS, f"unknown skill in template: {_s}"
