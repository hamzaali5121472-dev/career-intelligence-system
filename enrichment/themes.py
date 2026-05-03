"""
Theme Taxonomy — B2Have Career Intelligence System
18 career themes + 6 audience segments used for AI enrichment and NLM categorization.
"""

CAREER_THEMES = [
    "ats_rejection",
    "job_search_fatigue",
    "interview_anxiety",
    "salary_negotiation",
    "career_change",
    "layoffs",
    "ai_replacing_jobs",
    "mental_health_burnout",
    "networking",
    "ghosting",
    "remote_vs_office",
    "credential_recognition",
    "imposter_syndrome",
    "overqualified_age_bias",
    "gta_canada_market",
    "coaching_worth_it",
    "employment_gap",
    "workplace_culture"
]

THEME_DESCRIPTIONS = {
    "ats_rejection": "ATS systems, automated resume screening, keyword optimization, black hole applications",
    "job_search_fatigue": "Burnout from job hunting, demoralization, hundreds of applications with no response",
    "interview_anxiety": "Fear of interviews, performance anxiety, freezing up, preparation stress",
    "salary_negotiation": "Negotiating offers, underpaid, counter-offers, market rate, pay equity",
    "career_change": "Switching industries, career pivots, transferable skills, reinvention",
    "layoffs": "Layoff experiences, job loss, severance, what to do after being laid off",
    "ai_replacing_jobs": "AI/automation job displacement anxiety, future of work, AI-proof skills",
    "mental_health_burnout": "Work burnout, toxic workplaces, work-life balance, job stress, work depression",
    "networking": "Professional networking, LinkedIn outreach, informational interviews, referrals",
    "ghosting": "Employer/recruiter ghosting, no follow-up after interviews, unprofessional hiring",
    "remote_vs_office": "Return-to-office mandates, remote work, hybrid policies, RTO resentment",
    "credential_recognition": "Foreign credentials in Canada, immigrant professionals, degree recognition",
    "imposter_syndrome": "Feeling unqualified, self-doubt, fear of being found out, confidence issues",
    "overqualified_age_bias": "Rejected for being overqualified, age discrimination, senior workers job searching",
    "gta_canada_market": "GTA/Toronto/Mississauga job market, Canadian employment trends, Ontario hiring",
    "coaching_worth_it": "Career coaching value, coach testimonials/complaints, coaching costs and ROI",
    "employment_gap": "Resume gaps, explaining time away from work, re-entering workforce",
    "workplace_culture": "Toxic culture, bad managers, micromanagement, company culture red flags"
}

AUDIENCE_SEGMENTS = [
    "new_graduate",
    "mid_career_pivot",
    "senior_executive",
    "immigrant_professional",
    "laid_off_urgent",
    "returning_to_workforce"
]

AUDIENCE_DESCRIPTIONS = {
    "new_graduate": "Recently graduated or 0-3 years experience. First real job, student loans, entry-level struggles.",
    "mid_career_pivot": "5-15 years experience wanting to change industries or roles. Has skills but needs direction.",
    "senior_executive": "15+ years, director/VP/C-suite level. Leadership transitions, executive job search.",
    "immigrant_professional": "Trained and experienced abroad, navigating Canadian job market. Credential issues, Canadian experience barrier.",
    "laid_off_urgent": "Recently laid off, urgent financial pressure, needs fast results.",
    "returning_to_workforce": "Returning after career break (parental leave, caregiving, illness, gap year). Confidence and re-entry challenges."
}
