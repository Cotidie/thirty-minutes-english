import random

TOPICS: tuple[str, ...] = (
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


def pick_topic(recent: list[str], rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    unused = [t for t in TOPICS if t not in set(recent)]
    return rng.choice(unused or list(TOPICS))
