---

> ## Challenge Advisor: Update & Finalize Your Project Overview
>
> > 💡 **These grey text instructions are just for you, the team's Challenge Advisor; please delete them once you have completed the steps below.**
>
> We've pre-populated this Challenge Project Overview page — which is what will be shared with your Break Through Tech student team in August — using the details from your submission form. You should have received an email inviting you to join this repo as a Collaborator, enabling you to add files and make edits.
> 
> In order for your project to be finalized and assigned to a team, please:
> 1. **Review all sections below** and update or expand any content as needed, making sure to address the SME Feedback in the section immediately below. Look for square brackets to find the places below that require additional inputs from you (e.g., "About [Company / Org Name]").
> 2. **Add your dataset** to the [data folder](data) in this repo.
> 3. **Close the Issue assigned to you in this repo** to let us know that you have made your edits and the overview page is ready for final review. You can do this by going to the _Issues_ tab in the top left section of the menu above, add a comment that says "CA review complete", and click the button to Close the Issue. 
>
> If you're unfamiliar with how to edit a page like this in GitHub, check out [this tutorial](https://ubc-lib-geo.github.io/gis-workshop-waml-template/content/handson/edit-readme.html) for a quick overview (start with step 2 and only edit this page), and [this guide](https://ubc-lib-geo.github.io/gis-workshop-waml-template/content/markdown.html) on how to use Markdown to compose text.
>
>
> ❌ Remember that this is a public repo. Do NOT include: Proprietary data, PII, API keys, credentials, or anything confidential.

## 📋 BTT Internal Evaluation Notes

| Check   | Status | Notes |
|---------|--------|-------|
| Python Compatibility | 🟢 | The project uses Python-based libraries and tools for data processing and modeling, aligning well with the student skill set. |
| Data Readiness  | 🟢 | The data is publicly available, under 1GB, and in accessible formats (CSV/TSV, JSON), which minimizes cleaning time and ensures readiness for use. |
| Resource Check  | 🟢 | The project can utilize free resources like Google Colab, and necessary API keys will be provided, ensuring access to required tools without additional cost burdens. |

**Student Fit Score:** 8/10  
**Technical Depth Score:** 7/10  
**Overall Recommendation:** REVISE

**Advisor Feedback Draft:**
The project demonstrates a clear understanding of how to leverage LLMs in a practical context. However, it would benefit from a more defined approach to the evaluation metrics to ensure they align well with real-world applications. Refinement in methodology for handling diverse code samples is advisable. I recommend a focus on iterating the framework based on early test results.

[Detail SME Project Feedback](./SME_Feedback.md)
---

# Building High-Quality Datasets and Evaluation Frameworks for AI Coding Assistants

**Company / Org:** Anote  
**Challenge Advisor:** Natan Vidra, nvidra@anote.ai.  
**AI Studio Coach:** Bhavya Gopal, bhavya.gopal@breakthroughtech.ai.  
**Program:** Break Through Tech AI Studio - Fall 2026

---

## 🏢 About Anote

Anote is focused on enhancing developer productivity through innovative AI solutions in the tech industry. Our solutions harness the power of AI to support coding, debugging, and understanding code, aiming to transform the developer experience and improve software quality.

---

## 🎯 The Challenge

### Project Summary
In this project, you will use code datasets, developer interactions, and code evaluation benchmarks and large language models (LLMs), supervised fine-tuning, and evaluation techniques to build and evaluate an AI system that improves code generation, debugging, and code understanding performance. This will help our company address the challenge of improving accuracy, reliability, and evaluation of AI-powered coding assistants in real-world development environments.

### Success Criteria
_Quantitative Metrics:_ 
- Pass@k (does generated code pass test cases)
- Functional correctness (unit test success rate)
- Accuracy of bug fixes / code transformations
- Reduction in error rate vs baseline models

_Qualitative Metrics:_
- Code readability and quality
- Developer usefulness (does output solve the task effectively)

_Final Outcome (December):_
- A working evaluation framework for AI coding models
- A curated dataset for code tasks (generation, fixing, testing)
- Demonstrated improvement vs baseline models
- A reproducible pipeline for benchmarking coding assistants

### Stretch Goals
- Build a real-time evaluation system integrated into the Anote coding assistant
- Add reinforcement learning / feedback loops (RLHF or RLAIF)
- Expand to multi-file or full-repo reasoning
- Add code execution environments (sandbox testing)
- Create a leaderboard comparing models (Claude, GPT, open-source)
- Incorporate human-in-the-loop feedback pipelines (core to Anote’s approach

### Project Milestones

Use these milestones to guide your work. Your team will create a **GitHub Projects board** to track tasks within each milestone.

| Month | Milestone | Key Activities |
|---|---|---|
| September | Foundations & Data | • Define project scope (e.g., code generation, bug fixing, or code explanation)<br>• Curate or construct a dataset:<br>&nbsp;&nbsp;&nbsp;&nbsp;◦ Code snippets + prompts (e.g., "fix this function," "generate unit tests")<br>&nbsp;&nbsp;&nbsp;&nbsp;◦ Ground truth outputs (correct code / expected behavior)<br>• Perform data preprocessing and formatting<br>• Establish baseline models (e.g., GPT/Claude or open-source LLMs)<br>• Define evaluation metrics (accuracy, pass@k, etc.) |
| October | Modeling & Evaluation | • Fine-tune or adapt models on curated datasets (if feasible)<br>• Build evaluation pipelines:<br>&nbsp;&nbsp;&nbsp;&nbsp;◦ Functional correctness testing (unit tests)<br>&nbsp;&nbsp;&nbsp;&nbsp;◦ Code similarity / semantic correctness scoring<br>• Run experiments comparing:<br>&nbsp;&nbsp;&nbsp;&nbsp;◦ Zero-shot vs fine-tuned models<br>• Analyze performance gaps and failure cases |
| November | Optimization & Integration | • Improve dataset quality (add edge cases, error cases, difficult prompts)<br>• Iterate on model + evaluation pipeline<br>• Integrate outputs into a simple interface:<br>&nbsp;&nbsp;&nbsp;&nbsp;◦ CLI tool, notebook, or lightweight UI<br>• Produce final benchmarking report<br>• Prepare demo showcasing improved coding assistant performance |

> **Note for the team:** Please create a GitHub Projects board in this repository to break these milestones into weekly tasks. Go to the **Projects** tab → **New project** → Choose **Board** → Add columns for each month.

---

## 📊 Dataset

**Name and Source:** Harbor Framework public dataset
**Format:** CSV, JSON  
**Size:** under 1gb  
**Location:** https://github.com/harbor-framework/terminal-bench/

### Key Details
- Terminal-Bench is a benchmark and execution harness for evaluating how well AI agents perform real, end-to-end tasks in a sandboxed terminal environment (e.g., compiling code, debugging, resolving security issues), maintained by the Harbor project.
- Harbor (https://github.com/harbor-framework/harbor) is the companion framework used to run and score agents against the benchmark — it supports evaluating agents like Claude Code, OpenHands, and Codex CLI, and can generate rollouts usable for RL-style fine-tuning.
- Tasks and results are tracked on the public Harbor Hub leaderboard; students should review the repo's README and tasks/ directory for the task schema and scoring rubric before building on top of it.
- Related repos worth skimming for structure/format reference: terminal-bench-2-1 (current verified task set) and frontier-bench (successor benchmark with harder tasks).
---

## 🛠️ Suggested Approach

**ML Problem Type:** Natural Language Processing (NLP), Large Language Models (LLMs)/ Generative AI, Transfer Learning / Pre-trained Models

**Recommended Libraries:**
- pandas / numpy for data wrangling and prompt–response dataset construction
- Hugging Face transformers / datasets for loading and fine-tuning open-source LLMs
- pytest or task-specific test harnesses for functional correctness scoring
- docker (via the Harbor/Terminal-Bench harness) for sandboxed code execution
- OpenAI / Anthropic Python SDKs for baseline zero-shot / few-shot comparisons

**Evaluation Metrics:**
- Pass@k
- Unit test pass rate / functional correctness
- Code similarity metrics (e.g., CodeBLEU) for semantic correctness scoring
- Error-rate reduction vs. baseline model outputs

---

## 📚 Resources to Get Started

The following resources will help your team understand the problem space and potential technical approaches for this project:

**Background Reading:**
- Harbor framework overview and documentation: https://github.com/harbor-framework/harbor
- Terminal-Bench project overview: https://github.com/harbor-framework/terminal-bench

**Technical Tutorials:**
- Harbor Cookbook (end-to-end examples for running and building benchmarks): linked from the Harbor repo README
- Hugging Face documentation for fine-tuning and evaluating LLMs on code tasks

**Code Examples:**
- harbor-framework/terminal-bench-2-1 — current verified task set and submission workflow
- harbor-framework/frontier-bench — successor benchmark, useful reference for task structure

**Other:**
- [Links to any additional resources — e.g., papers, videos, podcasts, etc.]

*Feel free to explore beyond these, and share anything interesting you find with me!*

---

## 🤝 How We'll Work Together

**Official check-ins:** During our biweekly 45-minute AI Studio Lab Section meeting block (2nd and 4th week of every month)

 **Other ways to reach out to me with questions:** 
* Your team's channel within Break Through Tech’s Discord space
* Rashmithimmaraju14@gmail.com; please copy your teammates and AI Studio Coach
* Request a team check-in on Zoom
* Note: I will aim to respond within 48 hours. Please reach out to your AI Studio Coach with urgent questions.

> 💡 **Challenge Advisor: Please update the above based on your availability and preference. If you are not able to answer questions or meet with fellows outside of the biweekly Lab Section check-ins, simply write in "N/A (only available during the official check-in times)"**


---

## 🚀 Getting Started

1. **Review this overview document** and note any questions for our first meeting
2. **Begin reviewing the dataset** using the link above
3. **Read the GitHub Projects documentation** [here](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects)

I’m excited to work with you!

---

## ❓ Questions?

Please bring any questions to our first meeting during the week of August 24th (Break Through Tech’s Bridge to Studio - Session C). 
