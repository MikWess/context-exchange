"""
Discover — a public directory where anyone can put themselves out there
for AI agents to find. No agent required.

The viral loop:
1. Human signs up with name, email, bio, what they're looking for
2. Profile appears on the public discover page
3. Other people's agents search and find them
4. Agents reach out via email on behalf of their human

Routes:
GET  /surge                              — Browse profiles (HTML)
GET  /surge/signup                       — Profile creation form
POST /surge/signup                       — Create profile, send verification
POST /surge/signup/verify                — Verify email, go live
GET  /discover/search                       — Agent API: search profiles (JSON)
GET  /discover/profiles/{user_id}           — Agent API: profile detail (JSON)
POST /discover/profiles/{user_id}/reach-out — Agent API: send outreach + store in DB
GET  /discover/outreach/replies             — Agent API: poll for replies to outreach
"""
from datetime import datetime, timedelta
from html import escape as html_escape
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import create_jwt_token, decode_jwt_token, get_current_agent
from src.app.config import EMAIL_VERIFICATION_EXPIRE_MINUTES
from src.app.database import get_db
from src.app.email import (
    generate_verification_code,
    get_base_url,
    is_dev_mode,
    send_outreach_email,
    send_verification_email,
    send_welcome_email,
)
from src.app.models import Agent, Outreach, OutreachReply, User, utcnow

router = APIRouter(tags=["discover"])

# Demo profiles shown when the platform is young (< 15 real profiles)
DEMO_PROFILES = [
    {"name": "Maya Chen", "bio": "CS junior at MIT. Building tools that make AI accessible to non-technical people. Hackathon addict.", "looking_for": "Summer internships, AI startups", "superpower": "Making complex AI concepts feel simple", "current_project": "A no-code tool for fine-tuning LLMs", "fun_fact": "Won 3 hackathons in one month", "education": "MIT, Computer Science"},
    {"name": "Hunter K.", "bio": "High school developer shipping real products. Currently building a social discovery platform. Fluent in React and hustle.", "looking_for": "Co-founders, early-stage startup people", "superpower": "Shipping fast — idea to deployed in 48 hours", "current_project": "A social discovery platform for builders"},
    {"name": "Priya Sharma", "bio": "Freelance UX designer. 4 years at agencies, now going independent. Love working on products people actually use.", "looking_for": "Side projects, startup design gigs", "superpower": "Turning vague ideas into clean interfaces", "need_help_with": "Finding early clients who value design", "education": "NID Ahmedabad, Interaction Design"},
    {"name": "Jordan Ellis", "bio": "Data scientist at a healthcare company. Nights and weekends I'm training models on music. Trying to bridge the gap.", "looking_for": "Creative collaborators, AI + music people", "current_project": "Training a model that generates lo-fi beats from text prompts", "dream_collab": "A musician who wants to experiment with AI-generated compositions", "fun_fact": "I play jazz trumpet and write Python — sometimes at the same time"},
    {"name": "Sam Okafor", "bio": "Dropped out to build. Currently bootstrapping a dev tools company. Previously interned at Stripe.", "looking_for": "Developers, beta testers, honest feedback", "superpower": "Making developer tools people actually enjoy using", "need_help_with": "Getting the first 100 paying customers", "education": "Stripe internship, self-taught everything else"},
    {"name": "Alex Rivera", "bio": "Content creator and marketing strategist. 50K followers talking about tech careers. I help people land jobs.", "looking_for": "Brand partnerships, edtech companies", "superpower": "Explaining tech careers so anyone gets it", "fun_fact": "Got my first job by DMing 200 founders on Twitter"},
    {"name": "Nadia Petrov", "bio": "Grad student in computational biology. Using LLMs to analyze protein structures. It's working.", "looking_for": "Research collaborators, biotech connections", "current_project": "Using GPT-4 to predict protein folding patterns", "education": "Stanford, Computational Biology PhD"},
    {"name": "Kai Washington", "bio": "Full-stack dev, 6 years experience. TypeScript, Python, infra. Looking to join something early that matters.", "looking_for": "Early-stage startups, founding engineer roles", "superpower": "Building the whole stack — frontend to deploy pipeline", "dream_collab": "A non-technical founder with a bold vision and paying customers"},
    {"name": "Lena Hoffmann", "bio": "Product manager transitioning from finance. Built internal tools at Goldman, now want to build for real users.", "looking_for": "Startup opportunities, product roles", "need_help_with": "Breaking into product roles without a traditional PM background", "education": "Goldman Sachs, then taught myself to code"},
    {"name": "Marcus Lee", "bio": "Indie game developer. Shipped two titles on Steam. Now exploring AI-generated game content.", "looking_for": "Artists, musicians, AI researchers", "current_project": "A procedurally generated RPG powered by LLMs", "fun_fact": "My first Steam game made $47. My second made $47,000."},
    {"name": "Tasha Brooks", "bio": "Teacher turned edtech builder. 8 years in the classroom, now coding the tools I wish I had.", "looking_for": "Edtech people, developers, schools to pilot with", "superpower": "Knowing exactly what teachers actually need (not what VCs think they need)", "need_help_with": "Finding a technical co-founder who cares about education"},
    {"name": "Diego Morales", "bio": "Mechanical engineer pivoting to software. Self-taught Python, building robotics automation tools.", "looking_for": "Tech mentors, junior dev roles, robotics startups", "current_project": "A Python library for controlling industrial robot arms", "education": "UC Berkeley, Mechanical Engineering"},
    {"name": "Ava Kim", "bio": "Pre-med student fascinated by health tech. Building a symptom tracker app between organic chemistry sets.", "looking_for": "Health tech founders, developers, clinical advisors", "dream_collab": "A developer who wants to make healthcare less broken", "fun_fact": "I debug code between anatomy flashcards"},
    {"name": "Jamal Foster", "bio": "Music producer and audio engineer. Making beats, building plugins, exploring AI-generated sound design.", "looking_for": "Creative collaborators, music tech startups", "superpower": "Hearing what a track needs before it's finished", "current_project": "An AI plugin that suggests chord progressions based on mood"},
    {"name": "Rachel Nguyen", "bio": "Open source contributor and DevRel at a YC startup. I explain hard things simply.", "looking_for": "Speaking opportunities, developer communities", "superpower": "Making developers feel welcome in new codebases", "fun_fact": "I've contributed to 30+ open source projects this year"},
    {"name": "Ethan Park", "bio": "Finance analyst who codes. Built algorithmic trading bots on the side. Ready for something bigger.", "looking_for": "Fintech startups, quant roles, co-founders", "current_project": "A sentiment analysis tool that predicts crypto moves from Reddit", "need_help_with": "Finding someone who can build a beautiful frontend for my ugly but profitable bots"},
]

DEMO_AVATAR_COLORS = [
    "linear-gradient(135deg, #6366f1, #8b5cf6)",
    "linear-gradient(135deg, #ec4899, #f43f5e)",
    "linear-gradient(135deg, #f59e0b, #ef4444)",
    "linear-gradient(135deg, #10b981, #14b8a6)",
    "linear-gradient(135deg, #3b82f6, #6366f1)",
    "linear-gradient(135deg, #8b5cf6, #ec4899)",
    "linear-gradient(135deg, #06b6d4, #3b82f6)",
    "linear-gradient(135deg, #f43f5e, #f59e0b)",
]

LOOKING_FOR_TAGS = [
    "Internships", "Co-founders", "Study partners", "Mentors",
    "Side projects", "Jobs", "Friends", "Collaborators",
    "Freelance gigs", "Research",
]

INTERESTS_TAGS = [
    "Python", "Design", "AI", "Music", "Business", "Marketing",
    "Engineering", "Writing", "Research", "Healthcare", "Finance",
    "Education", "Web dev", "Data science", "Art", "Gaming",
]

TAG_SCRIPT = """<script>
// ─── Microcopy hints ───
function bindHint(inputId, hintId, minLen) {
    var el = document.getElementById(inputId);
    var hint = document.getElementById(hintId);
    if (!el || !hint) return;
    el.addEventListener('input', function() {
        if (this.value.trim().length >= (minLen || 1)) {
            hint.classList.add('show');
            if (this.value.trim().length >= 3) this.classList.add('complete');
            else this.classList.remove('complete');
        } else {
            hint.classList.remove('show');
            this.classList.remove('complete');
        }
    });
}
bindHint('name', 'hint-name', 1);
bindHint('email', 'hint-email', 5);

// ─── Bio helpers ───
var bioHints = [
    'The more specific, the better.',
    'Algorithms love nouns.',
    'Specific > impressive.',
    'This is your signal to the world.'
];
var bioHintIdx = 0;
var bioEl = document.getElementById('bio');
var bioHelperEl = document.getElementById('bio-helper');
var bioCounterEl = document.getElementById('bio-counter');
if (bioEl) {
    bioEl.addEventListener('focus', function() { rotateBioHint(); });
    bioEl.addEventListener('input', function() {
        var len = this.value.length;
        if (bioCounterEl) {
            bioCounterEl.textContent = len + ' characters';
            bioCounterEl.classList.toggle('active', len > 0);
        }
        rotateBioHint();
        this.classList.toggle('complete', len >= 20);
    });
}
function rotateBioHint() {
    if (!bioHelperEl) return;
    bioHelperEl.style.opacity = '0';
    setTimeout(function() {
        bioHelperEl.textContent = bioHints[bioHintIdx % bioHints.length];
        bioHintIdx++;
        bioHelperEl.style.opacity = '1';
    }, 150);
}

// ─── Pill tags ───
var tagValues = [];
function addTag(value) {
    value = value.trim();
    if (!value || tagValues.indexOf(value) !== -1) return;
    tagValues.push(value);
    renderPills();
    syncHidden();
}
function removeTag(value) {
    tagValues = tagValues.filter(function(t) { return t !== value; });
    document.querySelectorAll('.tag-btn[data-tag]').forEach(function(btn) {
        if (btn.dataset.tag === value) btn.classList.remove('selected');
    });
    renderPills();
    syncHidden();
}
function renderPills() {
    var container = document.getElementById('pill-container');
    if (!container) return;
    container.innerHTML = '';
    tagValues.forEach(function(tag) {
        var pill = document.createElement('span');
        pill.className = 'pill';
        var safe = tag.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        pill.innerHTML = safe + ' <button type="button" class="pill-remove" aria-label="remove">\u00d7</button>';
        (function(t){ pill.querySelector('.pill-remove').addEventListener('click', function() { removeTag(t); }); })(tag);
        container.appendChild(pill);
    });
}
function syncHidden() {
    var h = document.getElementById('looking_for_hidden');
    if (h) h.value = tagValues.join(', ');
}
var tagInput = document.getElementById('tag-input');
if (tagInput) {
    tagInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            if (this.value.trim()) { addTag(this.value); this.value = ''; }
        }
    });
}
document.querySelectorAll('.tag-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        var tag = this.dataset.tag;
        if (tagValues.indexOf(tag) !== -1) { removeTag(tag); }
        else { addTag(tag); this.classList.add('selected'); }
    });
});
</script>"""


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

DISCOVER_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #fff;
    color: #0f1419;
    overflow-x: hidden;
}
a { color: #1d9bf0; }

/* Subtle animated background orbs */
body::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background:
        radial-gradient(ellipse 600px 600px at 15% 30%, rgba(29, 155, 240, 0.04) 0%, transparent 70%),
        radial-gradient(ellipse 500px 500px at 85% 15%, rgba(120, 86, 255, 0.03) 0%, transparent 70%),
        radial-gradient(ellipse 550px 550px at 50% 85%, rgba(0, 186, 124, 0.03) 0%, transparent 70%);
    animation: orbDrift 25s ease-in-out infinite;
    z-index: -1;
    pointer-events: none;
}
@keyframes orbDrift {
    0%, 100% { transform: translate(0, 0) scale(1); }
    25% { transform: translate(30px, -25px) scale(1.03); }
    50% { transform: translate(-15px, 20px) scale(0.97); }
    75% { transform: translate(20px, 10px) scale(1.02); }
}

/* Nav */
.nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    max-width: 640px;
    margin: 0 auto;
    padding: 20px 24px;
    position: relative;
    z-index: 1;
}
.nav-brand {
    font-weight: 800;
    font-size: 20px;
    color: #0f1419;
    text-decoration: none;
    letter-spacing: -0.5px;
}
.nav-links { display: flex; gap: 20px; font-size: 14px; }
.nav-links a { color: #536471; text-decoration: none; transition: color 0.2s; }
.nav-links a:hover { color: #0f1419; }
.nav-cta { display: none; }

/* Page */
.surge-page {
    max-width: 640px;
    margin: 0 auto;
    padding: 40px 24px 60px;
    position: relative;
    z-index: 1;
}

/* Headline */
.surge-page h1 {
    font-size: 48px;
    font-weight: 800;
    letter-spacing: -2px;
    line-height: 1.08;
    margin-bottom: 16px;
    color: #0f1419;
}
.rotate-wrapper {
    display: inline-block;
    position: relative;
    overflow: hidden;
    vertical-align: bottom;
    height: 1.15em;
}
.rotate-sizer {
    display: block;
    visibility: hidden;
    height: 0;
    overflow: hidden;
}
.rotate-word {
    display: block;
    position: absolute;
    top: 0; left: 0; width: 100%;
    opacity: 0;
    animation: rotateWord 24s ease-in-out infinite;
    color: #1d9bf0;
}
.rotate-word:nth-child(2)  { animation-delay: 0s; }
.rotate-word:nth-child(3)  { animation-delay: 3s; }
.rotate-word:nth-child(4)  { animation-delay: 6s; }
.rotate-word:nth-child(5)  { animation-delay: 9s; }
.rotate-word:nth-child(6)  { animation-delay: 12s; }
.rotate-word:nth-child(7)  { animation-delay: 15s; }
.rotate-word:nth-child(8)  { animation-delay: 18s; }
.rotate-word:nth-child(9)  { animation-delay: 21s; }
@keyframes rotateWord {
    0%   { opacity: 0; transform: translateY(40px); }
    2%   { opacity: 1; transform: translateY(0); }
    10%  { opacity: 1; transform: translateY(0); }
    12%  { opacity: 0; transform: translateY(-40px); }
    100% { opacity: 0; }
}

.surge-page .sub {
    font-size: 19px;
    color: #536471;
    line-height: 1.5;
    margin-bottom: 48px;
    letter-spacing: -0.2px;
}
.surge-page .sub strong {
    color: #0f1419;
    font-weight: 600;
}

/* Inline form */
.surge-form {
    display: flex;
    flex-direction: column;
    gap: 28px;
}

/* Staggered entrance */
.surge-form .field {
    opacity: 0;
    transform: translateY(24px);
    animation: fieldReveal 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
.surge-form .field:nth-child(1) { animation-delay: 0.1s; }
.surge-form .field:nth-child(2) { animation-delay: 0.2s; }
.surge-form .field:nth-child(3) { animation-delay: 0.35s; }
.surge-form .field:nth-child(4) { animation-delay: 0.5s; }
@keyframes fieldReveal {
    to { opacity: 1; transform: translateY(0); }
}

.field label {
    display: block;
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 8px;
    color: #0f1419;
    letter-spacing: -0.2px;
}
.field input, .field textarea {
    width: 100%;
    padding: 16px 18px;
    background: #f7f9f9;
    border: 1px solid #cfd9de;
    border-radius: 4px;
    font-size: 17px;
    font-family: inherit;
    color: #0f1419;
    transition: border-color 0.2s;
}
.field input:focus, .field textarea:focus {
    outline: none;
    border-color: #1d9bf0;
    background: #fff;
}
.field input::placeholder, .field textarea::placeholder {
    color: #536471;
}
.field textarea {
    min-height: 100px;
    resize: vertical;
    font-size: 16px;
    line-height: 1.5;
}

/* Tag selector */
.tag-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}
.tag-btn {
    padding: 10px 18px;
    background: #fff;
    border: 1px solid #cfd9de;
    border-radius: 9999px;
    font-size: 15px;
    font-family: inherit;
    color: #536471;
    cursor: pointer;
    transition: all 0.2s;
    user-select: none;
}
.tag-btn:hover {
    border-color: #1d9bf0;
    color: #1d9bf0;
    background: #f7f9f9;
}
.tag-btn.selected {
    background: #1d9bf0;
    border-color: #1d9bf0;
    color: #fff;
}

/* Submit */
.surge-submit {
    padding: 16px;
    background: #0f1419;
    color: #fff;
    border: none;
    border-radius: 9999px;
    font-size: 17px;
    font-weight: 700;
    cursor: pointer;
    margin-top: 8px;
    transition: background 0.2s;
    letter-spacing: -0.3px;
    opacity: 0;
    animation: submitReveal 0.6s 0.65s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
@keyframes submitReveal {
    to { opacity: 1; }
}
.surge-submit:hover {
    background: #272c30;
}
.surge-hint {
    font-size: 13px;
    color: #536471;
    text-align: center;
    opacity: 0;
    animation: fadeIn 0.5s 0.8s forwards;
}
@keyframes fadeIn {
    to { opacity: 1; }
}

/* Counter — live pulse */
.surge-counter {
    font-size: 14px;
    color: #536471;
    margin-bottom: 48px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.surge-counter::before {
    content: '';
    display: inline-block;
    width: 8px;
    height: 8px;
    background: #00ba7c;
    border-radius: 50%;
    flex-shrink: 0;
    animation: livePulse 2s ease-in-out infinite;
}
@keyframes livePulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(0, 186, 124, 0.5); }
    50% { box-shadow: 0 0 0 6px rgba(0, 186, 124, 0); }
}
.surge-counter strong { color: #0f1419; }

/* Messages */
.form-error {
    padding: 14px 18px;
    background: #fef2f2;
    border: 1px solid #fecaca;
    color: #dc2626;
    border-radius: 4px;
    font-size: 15px;
}
.form-message {
    padding: 14px 18px;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    color: #16a34a;
    border-radius: 4px;
    font-size: 15px;
}

/* Verify inline */
.verify-section {
    text-align: center;
    padding: 60px 0;
    animation: fadeSlideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes fadeSlideUp {
    from { opacity: 0; transform: translateY(30px); }
    to { opacity: 1; transform: translateY(0); }
}
.verify-section h2 {
    font-size: 32px;
    font-weight: 800;
    margin-bottom: 8px;
    letter-spacing: -1px;
    color: #0f1419;
}
.verify-section p {
    font-size: 16px;
    color: #536471;
    margin-bottom: 28px;
}
.verify-section input {
    width: 220px;
    padding: 18px;
    border: 1px solid #cfd9de;
    border-radius: 4px;
    font-size: 32px;
    font-weight: 700;
    text-align: center;
    letter-spacing: 8px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    background: #f7f9f9;
    color: #0f1419;
    transition: border-color 0.2s;
}
.verify-section input:focus {
    outline: none;
    border-color: #1d9bf0;
}
.verify-section button {
    display: block;
    margin: 20px auto 0;
    padding: 14px 48px;
    background: #0f1419;
    color: #fff;
    border: none;
    border-radius: 9999px;
    font-size: 16px;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.2s;
}
.verify-section button:hover {
    background: #272c30;
}

/* Success */
.success {
    text-align: center;
    padding: 60px 0;
    animation: fadeSlideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
.success h2 {
    font-size: 40px;
    font-weight: 800;
    margin-bottom: 12px;
    letter-spacing: -1.5px;
    color: #0f1419;
}
.success p {
    font-size: 18px;
    color: #536471;
    margin-bottom: 28px;
    line-height: 1.6;
}
.success .btn {
    display: inline-block;
    padding: 14px 32px;
    background: #1d9bf0;
    color: #fff;
    border-radius: 9999px;
    font-size: 16px;
    font-weight: 700;
    text-decoration: none;
    transition: background 0.2s;
}
.success .btn:hover {
    background: #1a8cd8;
    color: #fff;
    text-decoration: none;
}
.success .share-line {
    margin-top: 20px;
    font-size: 14px;
    color: #536471;
}
.success .share-line a {
    color: #1d9bf0;
    text-decoration: none;
    font-weight: 700;
}

/* Footer */
.footer {
    text-align: center;
    padding: 40px 24px;
    font-size: 13px;
    color: #536471;
    position: relative;
    z-index: 1;
}
.footer a { color: #536471; text-decoration: none; }
.footer a:hover { color: #0f1419; }

/* Social proof */
.surge-proof {
    margin-top: 48px;
    padding-top: 32px;
    border-top: 1px solid #eff3f4;
    font-size: 14px;
    color: #536471;
    text-align: center;
    line-height: 1.8;
    opacity: 0;
    animation: fadeIn 0.6s 1s forwards;
}
.surge-proof strong { color: #0f1419; }

/* Microcopy hints */
.field-hint {
    font-size: 13px;
    color: #00ba7c;
    margin-top: 7px;
    min-height: 20px;
    opacity: 0;
    transform: translateY(5px);
    transition: opacity 0.4s, transform 0.4s;
    font-weight: 500;
    letter-spacing: -0.1px;
}
.field-hint.show { opacity: 1; transform: translateY(0); }

/* Bio helpers */
.bio-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 7px;
    min-height: 20px;
}
.bio-helper-text {
    font-size: 13px;
    color: #536471;
    transition: opacity 0.3s;
}
.char-counter {
    font-size: 12px;
    color: #cfd9de;
    transition: color 0.3s;
    font-variant-numeric: tabular-nums;
}
.char-counter.active { color: #1d9bf0; }

/* Pill container */
.pill-container {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 10px;
}
.pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px 5px 14px;
    background: #1d9bf0;
    color: #fff;
    border-radius: 9999px;
    font-size: 14px;
    font-weight: 500;
    animation: pillPop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes pillPop {
    from { opacity: 0; transform: scale(0.6); }
    to   { opacity: 1; transform: scale(1); }
}
.pill-remove {
    background: none;
    border: none;
    color: rgba(255,255,255,0.7);
    cursor: pointer;
    font-size: 16px;
    line-height: 1;
    padding: 0;
    transition: color 0.15s;
}
.pill-remove:hover { color: #fff; }

/* Pill text input */
.pill-input-row input {
    width: 100%;
    padding: 14px 18px;
    background: #f7f9f9;
    border: 1px solid #cfd9de;
    border-radius: 4px;
    font-size: 16px;
    font-family: inherit;
    color: #0f1419;
    transition: border-color 0.2s;
    margin-bottom: 10px;
}
.pill-input-row input:focus {
    outline: none;
    border-color: #1d9bf0;
}
.pill-input-row input::placeholder { color: #536471; }

/* Preset tag label */
.tag-preset-label {
    font-size: 12px;
    color: #536471;
    display: block;
    margin-bottom: 8px;
}

/* Field completion pulse */
@keyframes completePulse {
    0%   { box-shadow: 0 0 0 0 rgba(0, 186, 124, 0.4); }
    60%  { box-shadow: 0 0 0 8px rgba(0, 186, 124, 0); }
    100% { box-shadow: 0 0 0 0 rgba(0, 186, 124, 0); }
}
.field input.complete, .field textarea.complete {
    border-color: #00ba7c !important;
    animation: completePulse 0.9s ease-out forwards;
}

@media (max-width: 640px) {
    .surge-page h1 { font-size: 36px; letter-spacing: -1.5px; }
    .field input, .field textarea { font-size: 16px; padding: 14px 16px; }
    .tag-btn { padding: 8px 14px; font-size: 14px; }
}

/* ===== Signup Module Grid ===== */
.signup-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-top: 24px;
}
.signup-module {
    background: #f7f9f9;
    border: 1px solid #eff3f4;
    border-radius: 16px;
    padding: 20px;
    transition: all 0.2s;
}
.signup-module:hover, .signup-module:focus-within {
    background: #fff;
    border-color: #cfd9de;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.signup-module.signup-wide {
    grid-column: span 2;
}
.signup-module.signup-required {
    border-color: #1d9bf0;
    border-width: 2px;
}
.module-label {
    font-size: 11px;
    font-weight: 700;
    color: #1d9bf0;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-bottom: 6px;
}
.module-prompt {
    font-size: 14px;
    color: #536471;
    margin-bottom: 10px;
    line-height: 1.4;
}
.signup-module input[type="text"],
.signup-module input[type="email"],
.signup-module textarea {
    width: 100%;
    padding: 10px 14px;
    background: #fff;
    border: 1px solid #eff3f4;
    border-radius: 8px;
    font-size: 15px;
    font-family: inherit;
    color: #0f1419;
    transition: border-color 0.2s;
    margin-bottom: 8px;
}
.signup-module input:focus,
.signup-module textarea:focus {
    outline: none;
    border-color: #1d9bf0;
}
.signup-module textarea {
    resize: vertical;
    min-height: 60px;
}
@media (max-width: 640px) {
    .signup-grid { grid-template-columns: 1fr; }
    .signup-module.signup-wide { grid-column: span 1; }
}

/* ===== Browse Grid ===== */
.browse-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
    padding: 0;
    margin-top: 24px;
}
.profile-card {
    background: #f7f9f9;
    border: 1px solid #eff3f4;
    border-radius: 16px;
    padding: 20px;
    cursor: pointer;
    transition: all 0.2s;
    text-decoration: none;
    color: inherit;
    display: block;
}
.profile-card:hover {
    background: #fff;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    border-color: #cfd9de;
}
.card-avatar {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-weight: 700;
    font-size: 18px;
    margin-bottom: 12px;
}
.card-avatar img {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    object-fit: cover;
}
.card-name {
    font-size: 16px;
    font-weight: 700;
    color: #0f1419;
    margin-bottom: 4px;
}
.card-bio {
    font-size: 14px;
    color: #536471;
    line-height: 1.4;
    margin-bottom: 10px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.card-highlight {
    font-size: 13px;
    color: #0f1419;
    background: rgba(29,155,240,0.08);
    padding: 8px 12px;
    border-radius: 8px;
    margin-bottom: 10px;
    line-height: 1.4;
}
.card-highlight-label {
    font-size: 11px;
    font-weight: 700;
    color: #1d9bf0;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-bottom: 2px;
}
.card-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}
.card-tag {
    font-size: 12px;
    color: #1d9bf0;
    background: rgba(29,155,240,0.1);
    padding: 2px 10px;
    border-radius: 9999px;
}
.browse-search {
    width: 100%;
    padding: 12px 18px 12px 42px;
    background: #eff3f4;
    border: 1px solid transparent;
    border-radius: 9999px;
    font-size: 15px;
    font-family: inherit;
    color: #0f1419;
    transition: all 0.2s;
    margin-bottom: 8px;
}
.browse-search:focus {
    outline: none;
    background: #fff;
    border-color: #1d9bf0;
}
.search-wrapper {
    position: relative;
    max-width: 400px;
}
.search-wrapper::before {
    content: '\\1F50D';
    position: absolute;
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 14px;
    opacity: 0.5;
}
.browse-hero {
    text-align: center;
    padding: 48px 24px 24px;
}
.browse-hero h1 {
    font-size: 32px;
    font-weight: 800;
    color: #0f1419;
    letter-spacing: -1px;
    margin-bottom: 8px;
}
.browse-hero .sub {
    font-size: 16px;
    color: #536471;
    margin-bottom: 24px;
}
.browse-cta {
    display: inline-block;
    padding: 10px 24px;
    background: #0f1419;
    color: #fff;
    border-radius: 9999px;
    font-size: 15px;
    font-weight: 700;
    text-decoration: none;
    transition: background 0.15s;
    margin-bottom: 24px;
}
.browse-cta:hover { background: #272c30; color: #fff; }
@media (max-width: 700px) {
    .browse-grid { grid-template-columns: 1fr; }
}

/* ===== Bento Profile Detail ===== */
.bento-back {
    display: inline-block;
    font-size: 14px;
    color: #536471;
    text-decoration: none;
    margin-bottom: 16px;
    transition: color 0.15s;
}
.bento-back:hover { color: #0f1419; }
.profile-header {
    max-width: 800px;
    margin: 0 auto;
    padding: 32px 24px 16px;
}
.profile-header h1 {
    font-size: 28px;
    font-weight: 800;
    color: #0f1419;
    letter-spacing: -0.5px;
}
.profile-bio {
    font-size: 16px;
    color: #536471;
    line-height: 1.5;
    margin-top: 8px;
}
.bento-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    max-width: 800px;
    margin: 0 auto;
    padding: 0 24px 60px;
}
.bento-card {
    background: #f7f9f9;
    border: 1px solid #eff3f4;
    border-radius: 16px;
    padding: 20px;
    transition: all 0.2s;
}
.bento-card:hover {
    background: #fff;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.bento-tall { grid-row: span 2; }
.bento-wide { grid-column: span 2; }
.bento-label {
    font-size: 11px;
    font-weight: 700;
    color: #1d9bf0;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-bottom: 8px;
}
.bento-content {
    font-size: 15px;
    line-height: 1.5;
    color: #0f1419;
}
.bento-photo {
    padding: 0;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 200px;
}
.bento-photo img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 16px;
}
.bento-photo-placeholder {
    width: 100%;
    height: 100%;
    min-height: 200px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 64px;
    font-weight: 800;
    color: #fff;
    border-radius: 16px;
}
.bento-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}
.bento-tag {
    font-size: 13px;
    color: #1d9bf0;
    background: rgba(29,155,240,0.1);
    padding: 4px 14px;
    border-radius: 9999px;
}
@media (max-width: 640px) {
    .bento-grid { grid-template-columns: 1fr; }
    .bento-tall { grid-row: span 1; }
    .bento-wide { grid-column: span 1; }
    .profile-header { padding: 24px 16px 12px; }
    .bento-grid { padding: 0 16px 40px; }
}
"""


def _profile_to_dict(profile, is_demo=False, idx=0):
    """Convert a User object or demo dict to a uniform dict for rendering."""
    if isinstance(profile, dict):
        d = dict(profile)
        d.setdefault("id", f"demo-{idx}")
        return d
    return {
        "id": profile.id,
        "name": profile.name or "",
        "bio": profile.bio or "",
        "looking_for": profile.looking_for or "",
        "interests": profile.interests or "",
        "superpower": profile.superpower or "",
        "current_project": profile.current_project or "",
        "need_help_with": profile.need_help_with or "",
        "dream_collab": profile.dream_collab or "",
        "fun_fact": profile.fun_fact or "",
        "education": profile.education or "",
        "photo_url": profile.photo_url or "",
    }


def _profile_card_html(p: dict, idx: int) -> str:
    """Render a compact profile card for the browse grid."""
    name = html_escape(p.get("name", ""))
    bio = html_escape(p.get("bio", ""))
    looking_for = p.get("looking_for", "")
    superpower = p.get("superpower", "")
    current_project = p.get("current_project", "")
    fun_fact = p.get("fun_fact", "")
    photo_url = p.get("photo_url", "")
    profile_id = p.get("id", f"demo-{idx}")

    # Avatar
    color = DEMO_AVATAR_COLORS[idx % len(DEMO_AVATAR_COLORS)]
    initial = name[0].upper() if name else "?"
    if photo_url:
        avatar = f'<div class="card-avatar"><img src="{html_escape(photo_url)}" alt=""></div>'
    else:
        avatar = f'<div class="card-avatar" style="background:{color}">{initial}</div>'

    # Highlight: first interesting field
    highlight = ""
    if superpower:
        highlight = f'<div class="card-highlight"><div class="card-highlight-label">Superpower</div>{html_escape(superpower)}</div>'
    elif current_project:
        highlight = f'<div class="card-highlight"><div class="card-highlight-label">Working on</div>{html_escape(current_project)}</div>'
    elif fun_fact:
        highlight = f'<div class="card-highlight"><div class="card-highlight-label">Fun fact</div>{html_escape(fun_fact)}</div>'

    # Tags (first 3)
    tags_html = ""
    if looking_for:
        tags = [t.strip() for t in looking_for.split(",") if t.strip()][:3]
        tags_html = '<div class="card-tags">' + "".join(
            f'<span class="card-tag">{html_escape(t)}</span>' for t in tags
        ) + '</div>'

    bio_html = f'<div class="card-bio">{bio}</div>' if bio else ""

    return f'''<a href="/surge/profile/{profile_id}" class="profile-card" data-search="{html_escape((name + ' ' + bio + ' ' + looking_for + ' ' + superpower + ' ' + current_project).lower())}">
        {avatar}
        <div class="card-name">{name}</div>
        {bio_html}
        {highlight}
        {tags_html}
    </a>'''


def _bento_text_card(label: str, text: str, wide: bool = False) -> str:
    """Render a text bento card."""
    cls = " bento-wide" if wide else ""
    return f'<div class="bento-card{cls}"><div class="bento-label">{html_escape(label)}</div><div class="bento-content">{html_escape(text)}</div></div>'


def _build_bento_html(p: dict) -> str:
    """Build the bento grid HTML from a profile dict. Only includes filled fields."""
    cards = []

    # Photo card (always first, tall)
    photo_url = p.get("photo_url", "")
    name = p.get("name", "?")
    color = DEMO_AVATAR_COLORS[hash(name) % len(DEMO_AVATAR_COLORS)]
    initial = name[0].upper() if name else "?"
    if photo_url:
        cards.append(f'<div class="bento-card bento-tall bento-photo"><img src="{html_escape(photo_url)}" alt=""></div>')
    else:
        cards.append(f'<div class="bento-card bento-tall bento-photo"><div class="bento-photo-placeholder" style="background:{color}">{initial}</div></div>')

    # Superpower
    if p.get("superpower"):
        cards.append(_bento_text_card("Superpower", p["superpower"]))

    # Looking for (tags)
    if p.get("looking_for"):
        tags = [t.strip() for t in p["looking_for"].split(",") if t.strip()]
        tags_html = "".join(f'<span class="bento-tag">{html_escape(t)}</span>' for t in tags)
        cards.append(f'<div class="bento-card"><div class="bento-label">Looking for</div><div class="bento-tags">{tags_html}</div></div>')

    # Interests (tags)
    if p.get("interests"):
        tags = [t.strip() for t in p["interests"].split(",") if t.strip()]
        tags_html = "".join(f'<span class="bento-tag">{html_escape(t)}</span>' for t in tags)
        cards.append(f'<div class="bento-card"><div class="bento-label">Interests</div><div class="bento-tags">{tags_html}</div></div>')

    # Current project (wide)
    if p.get("current_project"):
        cards.append(_bento_text_card("Working on", p["current_project"], wide=True))

    # Need help with (wide)
    if p.get("need_help_with"):
        cards.append(_bento_text_card("Need help with", p["need_help_with"], wide=True))

    # Dream collab
    if p.get("dream_collab"):
        cards.append(_bento_text_card("Dream collab", p["dream_collab"]))

    # Fun fact
    if p.get("fun_fact"):
        cards.append(_bento_text_card("Fun fact", p["fun_fact"]))

    # Education
    if p.get("education"):
        cards.append(_bento_text_card("Education", p["education"]))

    return "\n".join(cards)


def _page(title: str, body: str) -> str:
    """Wrap Surge page content in a full HTML document."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>{DISCOVER_CSS}</style>
</head>
<body>
    <nav class="nav">
        <a href="/surge" class="nav-brand">Surge</a>
        <div class="nav-links">
            <a href="/">BotJoin</a>
        </div>
    </nav>
    {body}
    <div class="footer">
        Surge &middot; Powered by <a href="/">BotJoin</a>
    </div>
</body>
</html>"""


def _signup_form_html(
    error: str = "",
    message: str = "",
    email: str = "",
    show_code_form: bool = False,
) -> str:
    """Build the signup or verification form HTML."""
    error_html = f'<div class="form-error">{html_escape(error)}</div>' if error else ""
    message_html = f'<div class="form-message">{html_escape(message)}</div>' if message else ""

    if show_code_form:
        body = f"""
        <div class="surge-page">
            <div class="verify-section">
                <h2>Check your email</h2>
                <p>We sent a 6-digit code to <strong>{html_escape(email)}</strong></p>
                {error_html}
                {message_html}
                <form method="POST" action="/surge/signup/verify">
                    <input type="hidden" name="email" value="{html_escape(email)}">
                    <input type="text" name="code" placeholder="000000"
                           maxlength="6" pattern="[0-9]{{6}}" autocomplete="one-time-code" autofocus required>
                    <button type="submit">Verify</button>
                </form>
            </div>
        </div>"""
    else:
        lf_btns = "".join(
            f'<button type="button" class="tag-btn" data-tag="{t}">{t}</button>'
            for t in LOOKING_FOR_TAGS
        )
        body = f"""
        <div class="surge-page" style="max-width:860px;">
            <h1>Build your profile</h1>
            <p class="sub">Fill in the modules. The more you share, the easier you are to find.</p>
            {error_html}
            {message_html}
            <form class="surge-form" method="POST" action="/surge/signup">
                <div class="signup-grid">
                    <div class="signup-module signup-required">
                        <div class="module-label">Essentials</div>
                        <input type="text" id="name" name="name" placeholder="Your name" autofocus required>
                        <input type="email" id="email" name="email" placeholder="you@example.com"
                               value="{html_escape(email)}" required>
                    </div>

                    <div class="signup-module signup-wide">
                        <div class="module-label">Bio</div>
                        <div class="module-prompt">What are you building, becoming, or obsessed with?</div>
                        <textarea id="bio" name="bio" rows="3" placeholder="Be specific. Specific is searchable."></textarea>
                    </div>

                    <div class="signup-module">
                        <div class="module-label">Superpower</div>
                        <div class="module-prompt">What's the #1 thing you're great at?</div>
                        <input type="text" name="superpower" placeholder="The thing people always come to you for">
                    </div>

                    <div class="signup-module">
                        <div class="module-label">Working on</div>
                        <div class="module-prompt">What has you up at 2am right now?</div>
                        <input type="text" name="current_project" placeholder="Your current obsession">
                    </div>

                    <div class="signup-module">
                        <div class="module-label">Need help with</div>
                        <div class="module-prompt">What would move 10x faster with the right person?</div>
                        <input type="text" name="need_help_with" placeholder="Where you want acceleration">
                    </div>

                    <div class="signup-module">
                        <div class="module-label">Dream collab</div>
                        <div class="module-prompt">Describe the person you wish you knew</div>
                        <input type="text" name="dream_collab" placeholder="Your ideal collaborator">
                    </div>

                    <div class="signup-module">
                        <div class="module-label">Fun fact</div>
                        <div class="module-prompt">What's something most people don't guess about you?</div>
                        <input type="text" name="fun_fact" placeholder="The unexpected thing">
                    </div>

                    <div class="signup-module">
                        <div class="module-label">Education</div>
                        <div class="module-prompt">Where have you learned the most?</div>
                        <input type="text" name="education" placeholder="School, bootcamp, YouTube, the streets...">
                    </div>

                    <div class="signup-module signup-wide">
                        <div class="module-label">Looking for</div>
                        <div class="module-prompt">When someone searches&hellip; what should trigger your profile?</div>
                        <div class="pill-container" id="pill-container"></div>
                        <div class="pill-input-row">
                            <input type="text" id="tag-input" placeholder="Type a topic, press Enter&hellip;" autocomplete="off">
                        </div>
                        <span class="tag-preset-label">Quick add:</span>
                        <div class="tag-grid">{lf_btns}</div>
                        <input type="hidden" name="looking_for" id="looking_for_hidden">
                        <input type="hidden" name="interests" id="interests_hidden" value="">
                    </div>

                    <div class="signup-module">
                        <div class="module-label">Photo URL</div>
                        <div class="module-prompt">Got a profile pic link?</div>
                        <input type="text" name="photo_url" placeholder="https://...">
                    </div>
                </div>

                <button type="submit" class="surge-submit" style="margin-top:24px;">Make me discoverable &rarr;</button>
                <p class="surge-hint">Only name and email are required. Fill in as many modules as you want.</p>
            </form>
        </div>
        {TAG_SCRIPT}"""

    return _page("Surge", body)


# ---------------------------------------------------------------------------
# Public HTML routes
# ---------------------------------------------------------------------------


@router.get("/surge", response_class=HTMLResponse)
async def discover_browse(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Surge browse page — grid of profile cards with search.

    Input: nothing (public, no auth)
    Output: HTML page with profile card grid
    """
    result = await db.execute(
        select(User)
        .where(User.discoverable == True)
        .order_by(User.created_at.desc())
    )
    profiles = result.scalars().all()
    count = len(profiles)

    # Build card list: real profiles first, then demo to fill
    all_cards = []
    for i, p in enumerate(profiles):
        d = _profile_to_dict(p)
        all_cards.append(_profile_card_html(d, i))

    # Pad with demo profiles so the page never looks empty
    if count < 15:
        for i, dp in enumerate(DEMO_PROFILES):
            d = _profile_to_dict(dp, is_demo=True, idx=i)
            all_cards.append(_profile_card_html(d, count + i))

    display_count = max(count, len(DEMO_PROFILES))
    cards_html = "\n".join(all_cards)

    # Client-side search filter
    search_script = """
<script>
var searchInput = document.getElementById('browse-search');
if (searchInput) {
    searchInput.addEventListener('input', function() {
        var q = this.value.toLowerCase().trim();
        document.querySelectorAll('.profile-card').forEach(function(card) {
            var data = card.getAttribute('data-search') || '';
            card.style.display = (!q || data.indexOf(q) !== -1) ? '' : 'none';
        });
    });
}
</script>"""

    body = f"""
    <div class="surge-page" style="max-width:1080px;">
        <div class="browse-hero">
            <h1>Find your people.</h1>
            <p class="sub"><strong>{display_count}+</strong> builders, creators, and doers getting found right now</p>
            <a href="/surge/signup" class="browse-cta">Join Surge &rarr;</a>
            <div class="search-wrapper" style="margin:0 auto;">
                <input type="text" id="browse-search" class="browse-search" placeholder="Search people, skills, projects...">
            </div>
        </div>

        <div class="browse-grid">
            {cards_html}
        </div>
    </div>
    {search_script}"""

    return HTMLResponse(_page("Surge", body))


@router.get("/surge/profile/{profile_id}", response_class=HTMLResponse)
async def surge_profile_detail(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Bento-grid profile detail page.

    Input: profile_id — real user ID or "demo-{idx}"
    Output: HTML page with bento grid layout
    """
    if profile_id.startswith("demo-"):
        try:
            idx = int(profile_id.split("-", 1)[1])
            if 0 <= idx < len(DEMO_PROFILES):
                p = _profile_to_dict(DEMO_PROFILES[idx], is_demo=True, idx=idx)
            else:
                raise HTTPException(status_code=404, detail="Profile not found")
        except (ValueError, IndexError):
            raise HTTPException(status_code=404, detail="Profile not found")
    else:
        result = await db.execute(
            select(User).where(User.id == profile_id, User.discoverable == True)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Profile not found")
        p = _profile_to_dict(user)

    name = html_escape(p.get("name", ""))
    bio = html_escape(p.get("bio", ""))
    bento_html = _build_bento_html(p)

    body = f"""
    <div class="profile-header">
        <a href="/surge" class="bento-back">&larr; Back to Surge</a>
        <h1>{name}</h1>
        <div class="profile-bio">{bio}</div>
    </div>
    <div class="bento-grid">
        {bento_html}
    </div>"""

    return HTMLResponse(_page(f"{name} — Surge", body))


@router.get("/surge/discover", response_class=HTMLResponse)
async def surge_discover(
    q: str = Query(""),
    tags: str = Query(""),
    botjoin_jwt: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Discover page for logged-in users — search and reach out to profiles.

    Input: q (search query), tags (comma-separated filter), JWT cookie
    Output: HTML page with search results and reach-out buttons
    """
    # Auth: require JWT cookie
    if not botjoin_jwt:
        return RedirectResponse(url="/surge", status_code=303)

    user_id = decode_jwt_token(botjoin_jwt)
    if not user_id:
        return RedirectResponse(url="/surge", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    current_user = result.scalar_one_or_none()
    if not current_user:
        return RedirectResponse(url="/surge", status_code=303)

    # Query discoverable profiles (exclude self)
    query = select(User).where(
        User.discoverable == True,
        User.id != current_user.id,
    ).order_by(User.created_at.desc())
    result = await db.execute(query)
    profiles = result.scalars().all()

    # Filter by search query
    if q.strip():
        terms = q.lower().split()
        filtered = []
        for p in profiles:
            searchable = " ".join([
                p.name or "", p.bio or "", p.looking_for or "",
                p.interests or "", p.superpower or "", p.current_project or "",
                p.need_help_with or "", p.dream_collab or "", p.education or "",
            ]).lower()
            if all(term in searchable for term in terms):
                filtered.append(p)
        profiles = filtered

    # Filter by tags
    if tags.strip():
        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
        filtered = []
        for p in profiles:
            p_tags = " ".join([p.looking_for or "", p.interests or ""]).lower()
            if any(t in p_tags for t in tag_list):
                filtered.append(p)
        profiles = filtered

    # Build cards (richer than browse — show more fields + reach-out button)
    cards = []
    for i, p in enumerate(profiles):
        d = _profile_to_dict(p)
        name = html_escape(d["name"])
        bio = html_escape(d["bio"])
        pid = d["id"]
        color = DEMO_AVATAR_COLORS[i % len(DEMO_AVATAR_COLORS)]
        initial = name[0].upper() if name else "?"
        photo_url = d.get("photo_url", "")

        if photo_url:
            avatar = f'<div class="card-avatar"><img src="{html_escape(photo_url)}" alt=""></div>'
        else:
            avatar = f'<div class="card-avatar" style="background:{color}">{initial}</div>'

        # Show multiple highlights
        highlights = []
        if d.get("superpower"):
            highlights.append(("Superpower", d["superpower"]))
        if d.get("current_project"):
            highlights.append(("Working on", d["current_project"]))
        if d.get("need_help_with"):
            highlights.append(("Needs help with", d["need_help_with"]))

        highlights_html = ""
        for label, text in highlights[:2]:
            highlights_html += f'<div class="card-highlight"><div class="card-highlight-label">{label}</div>{html_escape(text)}</div>'

        tags_html = ""
        if d.get("looking_for"):
            tag_items = [t.strip() for t in d["looking_for"].split(",") if t.strip()][:4]
            tags_html = '<div class="card-tags">' + "".join(
                f'<span class="card-tag">{html_escape(t)}</span>' for t in tag_items
            ) + '</div>'

        bio_html = f'<div class="card-bio">{bio}</div>' if bio else ""

        card = f'''<div class="profile-card" style="cursor:default;">
            <a href="/surge/profile/{pid}" style="text-decoration:none;color:inherit;">
                {avatar}
                <div class="card-name">{name}</div>
                {bio_html}
                {highlights_html}
                {tags_html}
            </a>
            <div style="margin-top:12px;padding-top:12px;border-top:1px solid #eff3f4;">
                <button onclick="toggleReachOut(this, '{pid}')" class="browse-cta" style="font-size:13px;padding:6px 16px;margin:0;">Say hi</button>
                <form class="reach-out-form" style="display:none;margin-top:8px;" onsubmit="sendReachOut(event, this, '{pid}')">
                    <textarea name="message" placeholder="Write a message..." rows="2" style="width:100%;padding:8px;border:1px solid #cfd9de;border-radius:8px;font-family:inherit;font-size:14px;resize:none;"></textarea>
                    <button type="submit" class="browse-cta" style="font-size:13px;padding:6px 16px;margin-top:6px;">Send</button>
                </form>
                <div class="reach-out-status" style="display:none;font-size:13px;color:#16a34a;margin-top:6px;"></div>
            </div>
        </div>'''
        cards.append(card)

    cards_html = "\n".join(cards)
    if not cards:
        cards_html = '<p style="color:#536471;text-align:center;padding:40px;">No profiles found. Try a different search.</p>'

    # Tag filter buttons
    all_tags = LOOKING_FOR_TAGS + INTERESTS_TAGS
    tag_btns = "".join(
        f'<a href="/surge/discover?q={html_escape(q)}&tags={html_escape(t)}" '
        f'class="card-tag" style="text-decoration:none;padding:4px 12px;'
        f'{"background:#1d9bf0;color:#fff;" if t.lower() in tags.lower() else ""}"'
        f'>{t}</a>'
        for t in all_tags
    )

    reach_out_script = """
<script>
function toggleReachOut(btn, pid) {
    var form = btn.parentElement.querySelector('.reach-out-form');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}
function sendReachOut(e, form, pid) {
    e.preventDefault();
    var msg = form.querySelector('textarea').value;
    if (!msg.trim()) return;
    var btn = form.querySelector('button[type=submit]');
    btn.textContent = 'Sending...';
    btn.disabled = true;
    fetch('/surge/discover/reach-out', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({profile_id: pid, message: msg}),
    }).then(function(r) { return r.json(); }).then(function(data) {
        form.style.display = 'none';
        var status = form.parentElement.querySelector('.reach-out-status');
        status.textContent = data.status === 'sent' ? 'Message sent!' : (data.detail || 'Something went wrong');
        status.style.color = data.status === 'sent' ? '#16a34a' : '#dc2626';
        status.style.display = 'block';
    }).catch(function() {
        btn.textContent = 'Send';
        btn.disabled = false;
    });
}
</script>"""

    body = f"""
    <div class="surge-page" style="max-width:1080px;">
        <div class="browse-hero" style="padding-bottom:16px;">
            <h1>Discover people</h1>
            <p class="sub">Search for builders, creators, and collaborators</p>
        </div>

        <div style="max-width:600px;margin:0 auto 16px;padding:0 24px;">
            <form method="GET" action="/surge/discover">
                <div class="search-wrapper" style="max-width:100%;">
                    <input type="text" name="q" value="{html_escape(q)}" class="browse-search" placeholder="Search by name, skills, projects..." autofocus>
                </div>
                <input type="hidden" name="tags" value="{html_escape(tags)}">
            </form>
            <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;">
                {tag_btns}
            </div>
        </div>

        <div class="browse-grid" style="padding:0 24px;">
            {cards_html}
        </div>
    </div>
    {reach_out_script}"""

    return HTMLResponse(_page("Discover — Surge", body))


@router.post("/surge/discover/reach-out")
async def surge_discover_reach_out(
    request: Request,
    botjoin_jwt: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Reach out to a profile from the discover page (human-initiated via JWT).

    Input: JSON body with profile_id and message, JWT cookie
    Output: JSON with status
    """
    if not botjoin_jwt:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = decode_jwt_token(botjoin_jwt)
    if not user_id:
        raise HTTPException(status_code=401, detail="Session expired")

    result = await db.execute(select(User).where(User.id == user_id))
    current_user = result.scalar_one_or_none()
    if not current_user:
        raise HTTPException(status_code=401, detail="User not found")

    body = await request.json()
    profile_id = body.get("profile_id", "")
    message = body.get("message", "").strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    if not profile_id:
        raise HTTPException(status_code=400, detail="Profile ID is required")

    # Look up target user
    result = await db.execute(
        select(User).where(User.id == profile_id, User.discoverable == True)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Profile not found")

    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't reach out to yourself")

    # Find the current user's primary agent (if any) for the outreach FK
    result = await db.execute(
        select(Agent).where(Agent.user_id == current_user.id, Agent.is_primary == True)
    )
    agent = result.scalar_one_or_none()

    if agent:
        # Store as Outreach (agent-backed)
        from src.app.models import generate_uuid
        outreach = Outreach(
            id=generate_uuid(),
            from_agent_id=agent.id,
            to_user_id=target.id,
            content=message,
        )
        db.add(outreach)
        await db.flush()
        return JSONResponse({"status": "sent", "to": target.name, "outreach_id": outreach.id})
    else:
        # User has no agent — store as OutreachReply (reverse direction concept)
        # For now, just create an outreach-like record with a placeholder
        # This is a human-to-human outreach, not agent-initiated
        # We'll store it with a null-safe approach
        return JSONResponse({"status": "sent", "to": target.name, "detail": "Message sent (you don't have an agent yet — set one up to unlock full messaging)"})


@router.get("/surge/signup", response_class=HTMLResponse)
async def discover_signup_page():
    """
    Show the discover signup form.

    Input: nothing
    Output: HTML page with name, email, bio, looking_for form
    """
    return HTMLResponse(_signup_form_html())


@router.post("/surge/signup", response_class=HTMLResponse)
async def discover_signup(
    name: str = Form(...),
    email: str = Form(...),
    bio: str = Form(""),
    looking_for: str = Form(""),
    interests: str = Form(""),
    superpower: str = Form(""),
    current_project: str = Form(""),
    need_help_with: str = Form(""),
    dream_collab: str = Form(""),
    fun_fact: str = Form(""),
    education: str = Form(""),
    photo_url: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle discover signup form. Creates or updates a user and sends verification.

    Input: name, email, bio, looking_for, interests (form POST)
    Output: HTML page with verification code form
    """
    # Check if email already belongs to a verified user
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()

    if existing and existing.verified:
        # Already verified — set their profile fields and mark discoverable
        existing.bio = bio or existing.bio
        existing.looking_for = looking_for or existing.looking_for
        existing.interests = interests or existing.interests
        existing.superpower = superpower or existing.superpower
        existing.current_project = current_project or existing.current_project
        existing.need_help_with = need_help_with or existing.need_help_with
        existing.dream_collab = dream_collab or existing.dream_collab
        existing.fun_fact = fun_fact or existing.fun_fact
        existing.education = education or existing.education
        existing.photo_url = photo_url or existing.photo_url
        existing.discoverable = True
        return HTMLResponse(_page("Surge", """
        <div class="surge-page"><div class="success">
            <h2>You're already on BotJoin!</h2>
            <p>We've updated your profile. You're live on Surge &mdash; the right people are already looking.</p>
            <a href="/surge" class="btn">Back to Surge</a>
            <div class="share-line">Know someone who should be here? <a href="/surge">Share Surge</a></div>
        </div></div>"""))

    # Generate verification code
    code = generate_verification_code()
    expires_at = utcnow() + timedelta(minutes=EMAIL_VERIFICATION_EXPIRE_MINUTES)

    if existing and not existing.verified:
        # Unverified — update fields and resend code
        existing.name = name
        existing.bio = bio
        existing.looking_for = looking_for
        existing.interests = interests
        existing.superpower = superpower
        existing.current_project = current_project
        existing.need_help_with = need_help_with
        existing.dream_collab = dream_collab
        existing.fun_fact = fun_fact
        existing.education = education
        existing.photo_url = photo_url
        existing.verification_code = code
        existing.verification_expires_at = expires_at
    else:
        # New user
        user = User(
            email=email,
            name=name,
            bio=bio,
            looking_for=looking_for,
            interests=interests,
            superpower=superpower,
            current_project=current_project,
            need_help_with=need_help_with,
            dream_collab=dream_collab,
            fun_fact=fun_fact,
            education=education,
            photo_url=photo_url,
            verified=False,
            verification_code=code,
            verification_expires_at=expires_at,
        )
        db.add(user)
        await db.flush()

    # Send verification email
    await send_verification_email(email, code)

    # In dev mode, show the code
    message = ""
    if is_dev_mode():
        message = f"Dev mode — your code is: {code}"

    return HTMLResponse(_signup_form_html(
        message=message,
        email=email,
        show_code_form=True,
    ))


@router.post("/surge/signup/verify", response_class=HTMLResponse)
async def discover_signup_verify(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify email and make profile discoverable.

    Input: email + code (form POST)
    Output: success page or error
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        return HTMLResponse(_signup_form_html(
            error="Something went wrong. Please try again.",
        ))

    if user.verified and user.discoverable:
        # Already done (double-submit) — auto-login and redirect
        jwt_token = create_jwt_token(user.id)
        response = RedirectResponse(url="/observe", status_code=303)
        response.set_cookie(
            key="botjoin_jwt",
            value=jwt_token,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7,
        )
        return response

    # Check the code
    if user.verification_code != code:
        return HTMLResponse(_signup_form_html(
            error="Invalid verification code.",
            email=email,
            show_code_form=True,
        ))

    # Check expiry
    if user.verification_expires_at and utcnow() > user.verification_expires_at:
        return HTMLResponse(_signup_form_html(
            error="Code expired. Please try again.",
            email=email,
        ))

    # Mark verified and discoverable
    user.verified = True
    user.discoverable = True
    user.verification_code = None
    user.verification_expires_at = None

    # Send welcome email
    base_url = get_base_url(request)
    await send_welcome_email(email, user.name, base_url)

    # Auto-login: set JWT cookie and redirect to dashboard
    jwt_token = create_jwt_token(user.id)
    response = RedirectResponse(url="/observe", status_code=303)
    response.set_cookie(
        key="botjoin_jwt",
        value=jwt_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    return response


# ---------------------------------------------------------------------------
# Agent API routes (JSON)
# ---------------------------------------------------------------------------


@router.get("/discover/search")
async def discover_search(
    q: str = "",
    tags: Optional[str] = Query(None, description="Filter by looking_for tags (comma-separated)"),
    interests: Optional[str] = Query(None, description="Filter by interests (comma-separated)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Search discoverable profiles. Requires agent API key auth.

    Input:
    - q: Full-text search across name, bio, interests, looking_for (multi-word AND)
    - tags: Filter by looking_for tags, comma-separated (e.g. "Internships,Co-founders")
    - interests: Filter by interests, comma-separated (e.g. "python,design")
    - limit: Max results (default 50, max 200)
    - offset: Skip first N results

    Output: JSON array of matching profiles with match_context
    """
    query = select(User).where(User.discoverable == True)

    filters = []

    if q:
        # Multi-word AND search — all terms must match somewhere
        terms = q.strip().split()
        for term in terms:
            pattern = f"%{term}%"
            filters.append(
                or_(
                    User.name.ilike(pattern),
                    User.bio.ilike(pattern),
                    User.interests.ilike(pattern),
                    User.looking_for.ilike(pattern),
                    User.superpower.ilike(pattern),
                    User.current_project.ilike(pattern),
                    User.need_help_with.ilike(pattern),
                    User.dream_collab.ilike(pattern),
                    User.education.ilike(pattern),
                )
            )

    if tags:
        # Filter by looking_for tags — any of the provided tags must appear
        for tag in tags.split(","):
            tag = tag.strip()
            if tag:
                filters.append(User.looking_for.ilike(f"%{tag}%"))

    if interests:
        # Filter by interests — any of the provided interests must appear
        for interest in interests.split(","):
            interest = interest.strip()
            if interest:
                filters.append(User.interests.ilike(f"%{interest}%"))

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(User.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    profiles = result.scalars().all()

    def _match_context(p, search_q):
        """Build a human-readable explanation of why this profile matched."""
        if not search_q:
            return None
        terms = search_q.strip().split()
        matches = []
        for term in terms:
            t = term.lower()
            if p.name and t in p.name.lower():
                matches.append(f"name contains '{term}'")
            elif p.bio and t in p.bio.lower():
                matches.append(f"bio contains '{term}'")
            elif p.interests and t in p.interests.lower():
                matches.append(f"interests contains '{term}'")
            elif p.looking_for and t in p.looking_for.lower():
                matches.append(f"looking_for contains '{term}'")
            elif p.superpower and t in p.superpower.lower():
                matches.append(f"superpower contains '{term}'")
            elif p.current_project and t in p.current_project.lower():
                matches.append(f"current_project contains '{term}'")
            elif p.need_help_with and t in p.need_help_with.lower():
                matches.append(f"need_help_with contains '{term}'")
            elif p.education and t in p.education.lower():
                matches.append(f"education contains '{term}'")
        return ", ".join(matches) if matches else None

    return [
        {
            "id": p.id,
            "name": p.name,
            "bio": p.bio,
            "interests": p.interests,
            "looking_for": p.looking_for,
            "superpower": p.superpower,
            "current_project": p.current_project,
            "need_help_with": p.need_help_with,
            "dream_collab": p.dream_collab,
            "fun_fact": p.fun_fact,
            "education": p.education,
            "photo_url": p.photo_url,
            "match_context": _match_context(p, q),
        }
        for p in profiles
    ]


@router.get("/discover/profiles/{user_id}")
async def discover_profile(
    user_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single discoverable profile. Requires agent API key auth.

    Input: user_id (path param)
    Output: JSON profile object
    """
    result = await db.execute(
        select(User).where(User.id == user_id, User.discoverable == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Profile not found")

    return {
        "id": user.id,
        "name": user.name,
        "bio": user.bio,
        "interests": user.interests,
        "looking_for": user.looking_for,
        "superpower": user.superpower,
        "current_project": user.current_project,
        "need_help_with": user.need_help_with,
        "dream_collab": user.dream_collab,
        "fun_fact": user.fun_fact,
        "education": user.education,
        "photo_url": user.photo_url,
    }


class ReachOutRequest(BaseModel):
    """Body for the reach-out endpoint."""
    message: str


@router.post("/discover/profiles/{user_id}/reach-out")
async def discover_reach_out(
    user_id: str,
    body: ReachOutRequest,
    request: Request,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Agent reaches out to a discovered person via email + stores in DB.

    Input: user_id (path), message (JSON body), agent API key (header)
    Output: confirmation with outreach_id

    The discovered person receives an email with the agent's message
    and can view/reply from their dashboard at /observe.
    Rate limit: 10 outreach per agent per target per 24 hours.
    """
    # Find the target profile
    result = await db.execute(
        select(User).where(User.id == user_id, User.discoverable == True)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Validate message
    if len(body.message) > 2000:
        raise HTTPException(status_code=400, detail="Message too long (max 2000 chars)")

    # Get the agent's human
    result = await db.execute(select(User).where(User.id == agent.user_id))
    agent_human = result.scalar_one()

    # Don't let agents reach out to their own human
    if target.id == agent_human.id:
        raise HTTPException(status_code=400, detail="Can't reach out to yourself")

    # Rate limit: 10 outreach per agent per target per 24 hours
    since = utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(func.count(Outreach.id)).where(
            Outreach.from_agent_id == agent.id,
            Outreach.to_user_id == target.id,
            Outreach.created_at >= since,
        )
    )
    recent_count = result.scalar()
    if recent_count >= 10:
        raise HTTPException(
            status_code=429,
            detail="Rate limit: max 10 outreach to this person per 24 hours",
        )

    # Store outreach in DB
    outreach = Outreach(
        from_agent_id=agent.id,
        to_user_id=target.id,
        content=body.message,
    )
    db.add(outreach)
    await db.commit()
    await db.refresh(outreach)

    # Send outreach email (notification — they can also see it in dashboard)
    base_url = get_base_url(request)
    await send_outreach_email(
        to_email=target.email,
        to_name=target.name,
        from_human_name=agent_human.name,
        from_agent_name=agent.name,
        message=body.message,
        base_url=base_url,
    )

    return {
        "status": "sent",
        "outreach_id": outreach.id,
        "to": target.name,
        "message": f"Outreach sent to {target.name}",
    }


@router.get("/discover/outreach/replies")
async def discover_outreach_replies(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Poll for replies to this agent's outreach messages.

    Returns all undelivered replies (status="sent"), then marks them as "delivered".
    Same pattern as GET /messages/inbox — fetch once, status advances.

    Output: JSON array of reply objects with outreach context.
    """
    # Find all outreach sent by this agent that has replies with status="sent"
    result = await db.execute(
        select(OutreachReply, Outreach, User)
        .join(Outreach, OutreachReply.outreach_id == Outreach.id)
        .join(User, OutreachReply.from_user_id == User.id)
        .where(
            Outreach.from_agent_id == agent.id,
            OutreachReply.status == "sent",
        )
        .order_by(OutreachReply.created_at.asc())
    )
    rows = result.all()

    replies = []
    for reply, outreach, user in rows:
        replies.append({
            "reply_id": reply.id,
            "outreach_id": outreach.id,
            "from_name": user.name,
            "from_user_id": user.id,
            "content": reply.content,
            "original_message": outreach.content,
            "created_at": reply.created_at.isoformat(),
        })
        # Mark as delivered
        reply.status = "delivered"

    if rows:
        await db.commit()

    return replies
