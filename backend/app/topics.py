import random
from datetime import date

from app.models import Category, Topic

_TECH: tuple[str, ...] = (
    "Digital twins in manufacturing",
    "Reinforcement learning for vehicle dispatching",
    "Automated material handling in semiconductor fabs",
    "Large language models as coding assistants",
    "Transformer attention explained for engineers",
    "Queueing theory and factory variability",
    "Predictive maintenance with sensor data",
    "Humanoid robots on the factory floor",
    "Vision-language-action models for robot manipulation",
    "Imitation learning from human demonstrations",
    "Simulation-to-real transfer in robotics",
    "Scheduling under uncertainty",
    "Supply chain resilience after disruptions",
    "Edge computing for real-time control",
    "Data quality and label noise in machine learning",
    "Federated learning and privacy",
    "Graph neural networks for logistics networks",
    "Diffusion models beyond image generation",
    "AI agents that use tools",
    "Evaluating LLMs: benchmarks and their limits",
    "Explainable AI for operations decisions",
    "Energy-aware computing in data centers",
    "Human-AI collaboration in engineering work",
    "The economics of automation and jobs",
    "Open-source versus proprietary AI models",
    "Anomaly detection in production lines",
    "Lean manufacturing meets machine learning",
    "Robot safety standards and certification",
    "Synthetic data for training perception models",
    "Optimization solvers versus learned heuristics",
)

_LITERATURE: tuple[str, ...] = (
    "Why Orwell's 1984 keeps returning to bestseller lists",
    "Kafka and the modern bureaucratic nightmare",
    "Han Kang and the international rise of Korean fiction",
    "The unreliable narrator from Nabokov to Ishiguro",
    "Dystopian fiction as social forecasting",
    "Science fiction that predicted real technology",
    "Why we still read Shakespeare",
    "The short story versus the novel",
    "Translation: what gets lost and what gets found",
    "Magical realism and Latin American history",
    "Poetry in the age of short attention spans",
    "Book bans and censorship battles today",
    "How literary prizes shape what the world reads",
    "Stoic philosophy's comeback in popular books",
    "Memoir and the ethics of writing about real people",
)

_HISTORY: tuple[str, ...] = (
    "The Silk Road and the first global trade network",
    "How the printing press changed who could think in public",
    "The Black Death and the end of medieval Europe",
    "The Meiji Restoration: modernizing a nation in one generation",
    "The Industrial Revolution and the birth of the factory",
    "The Cold War space race",
    "The fall of the Berlin Wall and the end of a divided world",
    "The Mongol Empire and the largest land empire in history",
    "Colonialism's economic legacy in Asia and Africa",
    "The 1918 flu pandemic and lessons for today",
    "The Korean War in global context",
    "The Ottoman Empire's rise and fall",
    "Why the Roman Republic became an empire",
    "The Age of Exploration and the Columbian Exchange",
    "Women's suffrage movements around the world",
    "The invention of the nation-state",
)

# Standing arguments rather than this week's headline: the generator searches for
# the latest turn in each, so the pool does not go stale between sessions.
_WORLD: tuple[str, ...] = (
    "The global race to regulate AI",
    "Semiconductor export controls and technological sovereignty",
    "Critical minerals and the battery supply chain",
    "Falling birth rates and shrinking workforces",
    "Aging societies and the arithmetic of pensions",
    "Housing costs in the world's big cities",
    "Migration and border politics in Europe",
    "The electricity bill of the AI boom",
    "Who pays for the energy transition",
    "Insurance retreating from places extreme weather keeps hitting",
    "Water scarcity and the future of farming",
    "Undersea cables and the security of the internet",
    "Space debris and the crowding of low orbit",
    "Weight-loss drugs and the budgets of health systems",
    "Antibiotic resistance as a slow-moving emergency",
    "Deep-sea mining and the rules nobody agreed on",
    "Elections in an age of synthetic media",
    "Remote work, five years on",
    "Food export bans and global prices",
    "Carbon border taxes and the trade fights they start",
)

# Home ground for a pair of Korean learners: the arguments Koreans have among
# themselves, phrased so the article can look for the latest turn in each.
_KOREA: tuple[str, ...] = (
    "Korea's birth rate and what could reverse it",
    "Mandatory military service in a shrinking Korea",
    "Hagwon culture and the price of a university seat",
    "Seoul housing prices and the jeonse lease system",
    "Chaebol power and the reform that never comes",
    "Korea's dependence on semiconductor exports",
    "Regional decline beyond the Seoul metro area",
    "Nuclear power's place in Korea's energy mix",
    "Foreign workers in Korea's factories and farms",
    "Korea's pension arithmetic and the retirement age",
    "K-pop as soft power and as an industry",
    "The gender divide among young Koreans",
    "Korea's long working hours and the four-day week",
    "Delivery apps and gig work in Korean cities",
    "Medical school quotas and the doctors' strikes",
    "Korean unification: goal, slogan, or memory",
    "Korea's suicide rate and the mental health taboo",
    "Living alone in Korea and the convenience store economy",
    "Korean food's global moment, from kimchi to gimbap",
    "Twelve years of English class and still afraid to speak",
    "Naver and Kakao against the global platforms",
    "AI and the future of Korean manufacturing jobs",
)

# The working life of two master's students: how research gets done, judged,
# published and paid for.
_RESEARCH: tuple[str, ...] = (
    "How to read a paper in an hour",
    "The reproducibility crisis in machine learning research",
    "Peer review: broken, or the least bad option",
    "Master's, PhD, or industry: what the extra years buy",
    "Working with an advisor who is never around",
    "Publish or perish and the rise of paper mills",
    "LLMs as co-authors: where the line is",
    "Open access and who pays for publishing",
    "Conference deadlines and the culture of the all-nighter",
    "Negative results and why nobody publishes them",
    "Citation counts as a measure of a scientist",
    "Writing a thesis nobody will read",
    "Presenting research to people outside your field",
    "Simulation results versus the real factory floor",
    "Industry-funded research and its blind spots",
    "Lab culture: hierarchy, hours, and burnout",
    "Choosing a research topic that is still open in three years",
    "Benchmarks, leaderboards, and what they hide",
    "Research ethics beyond the consent form",
    "Writing papers in a second language",
    "The gap between a paper's claim and its code",
    "Academic conferences: networking, tourism, or science",
)


def _pool(texts: tuple[str, ...], category: Category) -> tuple[Topic, ...]:
    return tuple(Topic(text=t, category=category) for t in texts)


TECH_TOPICS = _pool(_TECH, Category.TECH)
LITERATURE_TOPICS = _pool(_LITERATURE, Category.LITERATURE)
HISTORY_TOPICS = _pool(_HISTORY, Category.HISTORY)
WORLD_TOPICS = _pool(_WORLD, Category.WORLD)
KOREA_TOPICS = _pool(_KOREA, Category.KOREA)
RESEARCH_TOPICS = _pool(_RESEARCH, Category.RESEARCH)

TOPICS: tuple[Topic, ...] = TECH_TOPICS + LITERATURE_TOPICS + HISTORY_TOPICS + WORLD_TOPICS + KOREA_TOPICS + RESEARCH_TOPICS


def pool_for_day(day: date, count: int, exclude: list[str] | None = None, salt: int = 0) -> list[Topic]:
    """The same slice all day, a different one tomorrow. Seeded by the date, plus a
    salt so a manual refresh can deal a fresh slice within the day."""
    taken = set(exclude or ())
    available = [t for t in TOPICS if t.text not in taken]
    rng = random.Random(day.toordinal() * 1000 + salt)
    rng.shuffle(available)
    return available[: max(0, count)]


def pick_topic(recent: list[str], rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    unused = [t.text for t in TOPICS if t.text not in set(recent)]
    return rng.choice(unused or [t.text for t in TOPICS])
