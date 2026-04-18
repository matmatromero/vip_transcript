# Transcripts Agent ETL - Detailed Architecture Documentation

## Overview
A **multi-agent AI pipeline** that analyzes earnings call transcripts to extract strategic themes, supporting evidence, and dimensional classifications. Built on **Azure AI Agents** with parallel processing capabilities.

---

## Architecture Pattern
**Sequential Agent Chain with Batch Processing**

```
Raw Transcript → Agent 1 → Agent 2 → Agent 3 → Agent 4 → Agent 5 → Agent 6 → Final Output
```

---

## Agent Specifications

### **Agent 1: Theme Extraction**

**Purpose:** Extract all distinct strategic themes from earnings call transcripts

**Input:**
- Raw transcript text (plain text format)

**Output:**
```json
{
  "themes": [
    {
      "theme": "Short strategic title (max 10 words)",
      "summary": "Clear explanation (max 20 words)",
      "guidance": "Exhaustive explanation of what supporting sentences this theme should include"
    }
  ]
}
```

**Processing:**
- Mode: Single-threaded
- Batch Size: N/A (processes entire transcript at once)

**Key Responsibilities:**
1. Read full transcript
2. Identify every candidate strategic topic discussed by management
3. Split broad ideas into narrower themes when justified
4. Generate specific guidance for sentence assignment in next step
5. Generate max 20-word summary per theme
6. Ensure exhaustive and non-overlapping theme coverage

**Theme Extraction Philosophy:**
- **Exhaustive:** Capture all strategic discussions, including minor initiatives
- **Specific:** Prefer narrow, concrete topics over broad umbrellas
- **Strategic:** Focus on company-level direction, not tactical updates
- **Forward-looking:** Include anything strategy-relevant, even if subtle

**Theme Criteria:**
- Strategic company-level direction (not tactical updates)
- Answers: "What strategic direction is the company emphasizing?"
- Uses strategic phrasing: Strategy, Expansion, Transformation, Investment, Scaling, Optimization, Capability, Ecosystem, Positioning, Growth
- Includes operational updates only when they signal strategic direction

**Dimension Context (Directional):**
- Financial (Capital, Opex, Revenue, Others)
- Experience (Customer, Employee, Vendor/Partner)
- Sustainability (Environmental, Social, Governance)
- Talent (Change, Development)
- Inclusion & Diversity (Inclusive culture, Inclusive design, Team diversity)
- Custom (Innovation, new tech, unique strategies)

---

### **Agent 2: Supporting Sentences**

**Purpose:** Assign verbatim transcript evidence to each strategic theme

**Input:**
```json
{
  "transcript": "[Full transcript text]",
  "themes": [
    {
      "theme": "Theme name",
      "summary": "Theme summary",
      "guidance": "Exhaustive guidance on what supporting sentences to include",
      "transcript_id": "transcript_1",
      "is_latest": true
    }
  ]
}
```

**Output:**
```json
{
  "themes": [
    {
      "theme": "Theme name",
      "summary": "Theme summary",
      "guidance": "Guidance text",
      "transcript_id": "transcript_1",
      "is_latest": true,
      "supporting_sentences": [
        {
          "transcript_id": "transcript_1",
          "speaker": "Speaker name",
          "quote": "Verbatim quote from transcript (1-3 consecutive sentences)"
        }
      ]
    }
  ]
}
```

**Processing:**
- Mode: Batched parallel execution
- Batch Size: 3 themes per batch
- Concurrency: Up to 10 threads

**Key Responsibilities:**
1. Match each theme to its source transcript using transcript_id
2. Read full transcript
3. Understand themes and attached sentence assignment guidance
4. Assign sentences to each theme per guidance (exhaustive coverage)
5. Assign each sentence/chunk to exactly one best-fit theme
6. Check for duplicate evidence across themes and remove overlaps
7. Ensure final set is exhaustive

**Sentence Assignment Rules:**
- Supporting item may be:
  - One sentence (if self-contained)
  - 2-3 consecutive sentences (if context needed)
- Every supporting sentence/chunk becomes its own entry in array
- Include as many evidence entries as justified by guidance
- Use exact transcript wording
- Include speaker name if available

**Evidence Exclusivity Rule (CRITICAL):**
- Each sentence/chunk assigned to **only one** strategic theme
- If sentence fits multiple themes, assign to single most relevant theme
- Choose theme that is:
  1. Most specifically expressed by the sentence
  2. Most central to the meaning
  3. Least dependent on interpretation
- Before finalizing, check for duplicate evidence and remove all duplicates

---

### **Agent 3: Subtheme Grouping**

**Purpose:** Group related supporting sentences into logical subthemes within each theme

**Input:**
```json
{
  "themes": [
    {
      "theme": "Theme name",
      "summary": "Theme summary",
      "transcript_id": "transcript_1",
      "is_latest": true,
      "supporting_sentences": [
        {
          "transcript_id": "transcript_1",
          "speaker": "Speaker name",
          "quote": "Quote text"
        }
      ]
    }
  ]
}
```

**Output:**
```json
{
  "themes": [
    {
      "theme": "Theme name",
      "summary": "Theme summary",
      "transcript_id": "transcript_1",
      "is_latest": true,
      "subthemes": [
        {
          "subtheme": "Subtheme title",
          "supporting_sentences": [
            {
              "transcript_id": "transcript_1",
              "speaker": "Speaker name",
              "quote": "Quote text"
            }
          ]
        }
      ]
    }
  ]
}
```

**Processing:**
- Mode: Batched parallel execution
- Batch Size: 3 themes per batch
- Concurrency: Up to 10 threads

**Key Responsibilities:**
1. Treat sub-theme creation as a **clustering task**, not a labeling task
2. First cluster all sentences into 2-3 broad strategic buckets
3. Then name those buckets
4. Do not name each sentence separately

**Subtheme Rules (CRITICAL):**
- Work one theme at a time
- Review all sentences assigned to a theme together
- Define 2-3 broadest possible MECE-style sub-themes
- Only after broad sub-themes are defined, assign sentences
- Sub-themes must be broad buckets, not labels for individual sentences
- Use exactly 2-3 sub-themes in most cases
- Use 1 sub-theme only if theme is genuinely too narrow
- Do not create more than 3 sub-themes unless absolutely unavoidable
- Each sub-theme should contain multiple related sentences
- One-sentence sub-theme allowed only when truly distinct and cannot fit elsewhere
- Prefer fewer, broader sub-themes over many narrow ones

**Required Method:**
1. Review all supporting sentences for theme together
2. Identify 2-3 main strategic lenses that organize sentences
3. Name those lenses as sub-themes
4. Assign every sentence to best-fitting sub-theme
5. If any sub-theme has only one sentence, try merging unless it distorts meaning

**Hard Constraints:**
- Max 3 sub-themes per theme
- Avoid single-sentence sub-themes unless unavoidable

---

### **Agent 4: Dimension Tagging**

**Purpose:** Assign Dimensions and Sub-Dimensions to each theme based on strategic taxonomy

**Input:**
```json
{
  "themes": [
    {
      "theme": "Theme name",
      "summary": "Theme summary",
      "transcript_id": "transcript_1",
      "is_latest": true,
      "subthemes": [
        {
          "subtheme": "Subtheme title",
          "supporting_sentences": [
            {
              "transcript_id": "transcript_1",
              "speaker": "Speaker name",
              "quote": "Quote text"
            }
          ]
        }
      ]
    }
  ]
}
```

**Output:**
```json
{
  "themes": [
    {
      "theme": "Theme name",
      "summary": "Theme summary",
      "transcript_id": "transcript_1",
      "is_latest": true,
      "dimensions": ["Dimension1", "Dimension2"],
      "sub_dimensions": ["Sub-Dimension1", "Sub-Dimension2"],
      "subthemes": [
        {
          "subtheme": "Subtheme title",
          "supporting_sentences": [
            {
              "transcript_id": "transcript_1",
              "speaker": "Speaker name",
              "quote": "Quote text",
              "rationale": "Brief explanation of why dimensions apply to this sentence"
            }
          ]
        }
      ]
    }
  ]
}
```

**Processing:**
- Mode: Batched parallel execution
- Batch Size: 3 themes per batch
- Concurrency: Up to 10 threads

**Key Responsibilities:**
1. Assign appropriate Dimension(s) and Sub-Dimension(s) based on supporting sentences
2. Provide brief rationale explaining why assigned dimensions apply to each sentence
3. Use balanced judgment (not force-fitting)

**Core Principle (CRITICAL - BALANCED):**
Tagging must be done directionally based ONLY on:
1. Given dimension definitions
2. Theme context
3. Explicit meaning of the sentence
4. Company context and company control reflected in the sentence

**Decision Logic:**
- Tag if clear, reasonable company-context exists
- Do NOT add external knowledge
- Do NOT infer beyond what is reasonably implied
- Do NOT force-fit a sentence into a dimension

**Dimension Taxonomy:**

#### **1. Financial** - Measures financial value of program/project
- **Capital:** Impact on balance sheet (WC efficiency, CapEx efficiency)
  - Examples: Shorten inventory days, improve payables/receivables, shift to asset-light via cloud
- **Opex:** Impact on operational costs (COGS reductions, SG&A improvements)
- **Revenue:** Grow top-line (organic/inorganic growth, cross-sell, acquisition synergies)
- **Others:** Financial value not captured in Capital/Opex/Revenue

**When to assign Financial:**
- Sentence reflects company-level growth, monetization, scaling
- Cost efficiency or optimization
- Investment, capital deployment, infrastructure build
- Do NOT require explicit numbers, but avoid if financial implication is weak

#### **2. Experience** - Measures interactions and perceptions
- **Customer:** Strength of customer relationship, addressing needs, service level
- **Employee:** Strength of employee relationship, loyalty, advocacy
- **Vendor/Partner:** Strength of supplier relationship, enablement, satisfaction

**When to assign Experience:**
- Only when sentence reflects company interaction, service, experience, or relationship outcomes

#### **3. Sustainability** - Company-controlled actions impacting society, environment, governance
- **Environmental:** Company-driven impact on natural environment
  - Climate change (emissions, net zero), energy, water, waste, resources, biodiversity
- **Social:** Company impact on people and communities
  - Health & safety, labor practices, human rights, product safety, community engagement
  - Note: Societal/customer-facing inclusion (not internal representation → see I&D)
- **Governance:** Systems ensuring ethical, transparent, accountable operations
  - Board structure, ethics, compliance, risk management, data protection, internal controls

**Critical Guardrails:**
- **Environmental:** Tag when company actively manages/reduces/invests in environmental impact. Do NOT tag industry trends or global challenges without company action
- **Social:** Tag when company directly influences outcomes. Do NOT tag generic challenges without company-led action. Do NOT tag internal workforce capability (→ Talent)
- **Governance:** Tag when company implements/strengthens governance mechanisms. Do NOT tag geopolitical risks, macroeconomic uncertainty, or external risks without company response
- **ESG Guardrail:** Do NOT assign for geopolitical risks, macroeconomic conditions, industry-wide challenges, or regulatory mentions without company action. ESG requires clear company ownership/action

#### **4. Talent** - Future skills needs, skill gaps, upskilling
- **Change:** Ability to improve change readiness and workforce ability to respond to change
- **Development:** Ability to rapidly upskill and sustain workforce that applies skills to drive value

**When to assign Talent:**
- Only when company's own workforce capability, readiness, or skill development is clearly reflected

#### **5. Inclusion and Diversity**
- **Inclusive culture:** Meet diversity goals, improve representation across talent pipeline and supply chain
- **Inclusive design:** Embed inclusive design and accessibility (WCAG, responsible AI, bias testing)
- **Team diversity:** Improve measurable representation and inclusion indicators

**When to assign I&D:**
- Only when explicitly tied to company practices, design, or representation

#### **6. Custom**
- Anything that does not fit under above dimensions
- Examples: Innovation, new technology advancements, unique client-specific themes
- Has no Sub-Dimensions

**Anti-Force-Fit Rules (VERY IMPORTANT):**
- Do NOT stretch weak signals into dimensions
- Do NOT rely on keywords alone
- Do NOT ignore clear directional signals
- Do NOT default everything to Custom
- Use balanced judgment

**Assignment Rules:**
- A theme can map to multiple Dimensions (comma-separated)
- Each Dimension entry can have multiple Sub-Dimensions (comma-separated)
- Assign Dimension only if supporting sentences explicitly demonstrate value/impact
- Do not assign based on incidental or contextual mentions
- Never list Sub-Dimension without parent Dimension
- Custom Dimension has no Sub-Dimensions

---

### **Agent 5: Table Generation**

**Purpose:** Generate final structured CSV output with relevance scoring

**Input:**
```json
{
  "themes": [
    {
      "theme": "Theme name",
      "summary": "Theme summary",
      "transcript_id": "transcript_1",
      "is_latest": true,
      "dimensions": ["Dimension1"],
      "sub_dimensions": ["Sub-Dimension1"],
      "subthemes": [
        {
          "subtheme": "Subtheme title",
          "supporting_sentences": [
            {
              "transcript_id": "transcript_1",
              "speaker": "Speaker name",
              "quote": "Quote text",
              "rationale": "Explanation of dimensions"
            }
          ]
        }
      ]
    }
  ]
}
```

**Output:**
```json
{
  "rows": [
    {
      "transcript_id": "transcript_1",
      "dimension": "Dimension name",
      "theme": "Theme name",
      "theme_summary": "Theme summary",
      "sub_dimensions": "Sub-Dimension1, Sub-Dimension2",
      "subtheme": "Subtheme title",
      "sentence_summary": "5-7 word summary",
      "speaker": "Speaker name",
      "supporting_sentence": "Full quote text",
      "rationale": "Brief explanation",
      "relevance_score": 85
    }
  ]
}
```

**Processing:**
- Mode: Batched parallel execution
- Batch Size: 2 themes per batch
- Concurrency: Up to 10 threads

**Key Responsibilities:**
1. Create sentence summaries (5-7 words)
2. Assign relevance scores (0-100) using composite scoring
3. Generate final CSV-ready output

**Relevance Score Calculation (0-100):**

**Formula:**
```
Final Score = (Theme_Alignment × 0.5) + (Dimension_Fit × 0.3) + (Subtheme_Coherence × 0.2)
```

**1. Theme Alignment (0-100) - Weight: 50%**
How well does the sentence support the strategic theme?
- 90-100: Directly and explicitly addresses theme with strong evidence
- 70-89: Strongly relates with clear connection
- 50-69: Moderately relates
- 30-49: Tangentially relates
- 0-29: Weakly relates

**2. Dimension Fit (0-100) - Weight: 30%**
How strongly does the sentence demonstrate the assigned dimension's directional impact?
- 90-100: Clear, direct example of dimension definition; strong rationale
- 70-89: Clearly demonstrates dimension impact; solid rationale
- 50-69: Reasonable dimension alignment; adequate rationale
- 30-49: Weak dimension connection; generic/stretched rationale
- 0-29: Questionable dimension assignment; weak/forced rationale

**3. Subtheme Coherence (0-100) - Weight: 20%**
How well does the sentence fit within its subtheme grouping?
- 90-100: Central to subtheme's focus; perfect fit
- 70-89: Clearly belongs in this subtheme
- 50-69: Reasonably fits the subtheme
- 30-49: Marginal fit for this subtheme
- 0-29: Seems misplaced in this subtheme

**Format Requirements:**
- Each row contains ONE Dimension
- Include transcript_id to identify source transcript
- Include speaker name from supporting sentence
- sub_dimensions field contains comma-separated values if multiple
- Repeat theme and theme_summary across all rows for that theme
- Repeat subtheme across all supporting sentences that belong to it
- Each supporting sentence appears in only one row
- sentence_summary: 5-7 words maximum
- relevance_score: 0-100 integer (rounded)
- Output must be valid JSON only

---

### **Agent 6: Deduplication**

**Purpose:** Identify and remove repetitive themes across multiple transcripts

**Input:**
```json
{
  "rows": [
    {
      "transcript_id": "transcript_1",
      "theme": "Theme name",
      "theme_summary": "Theme summary",
      "row_index": 0
    }
  ]
}
```

**Output:**
```json
{
  "keep_indices": [0, 1, 5, 8, 12],
  "audit": [
    {
      "removed_theme": "Theme name from older transcript",
      "removed_from_transcript": "transcript_3",
      "kept_theme": "Theme name from newer transcript",
      "kept_in_transcript": "transcript_1",
      "reason": "Both themes address the same strategic topic: [brief explanation]"
    }
  ]
}
```

**Processing:**
- Mode: Multi-message workflow
- Batch Size: N/A (sends themes sequentially, then triggers)
- Workflow: Conversational context accumulation

**Key Responsibilities:**
1. Group rows by theme and transcript_id
2. Identify themes appearing in multiple transcripts with same strategic meaning
3. Determine which rows to keep (from most recent transcript)
4. Return row_index values of rows to keep
5. Document all removals in audit array

**Core Rule:**
If same strategic theme appears in more than one transcript, keep only rows from latest version (lowest transcript number) and remove all rows from older versions.

**How to Identify Repetition:**
Treat themes from different transcripts as repetitive if they represent the same core strategic management topic, even if:
- Theme names are worded differently
- Summaries are phrased differently

**Focus on strategic meaning, not exact text match.**

**Examples of Repetitive Themes:**
- "AI Scaling and Digital Transformation Strategy" vs "Digital Transformation and AI Deployment"
- "Cost Realignment and Reinvestment Strategy" vs "Cost Optimization and Margin Expansion Strategy"
- "Oncology Growth and Therapeutics Strategy" vs "Oncology Franchise Expansion Strategy"

**Recency Rule:**
Transcript recency determined by transcript_id:
- transcript_1 = MOST RECENT (keep this)
- transcript_2, transcript_3, transcript_4 = OLDER (remove if duplicate)

**Removal Rule:**
When removing older repetitive theme:
- Remove ALL rows belonging to that older theme from that older transcript
- Entire theme is removed, not just individual rows

**Keep Rule:**
Keep a theme if:
- It is unique to that transcript, OR
- It is the most recent occurrence of that strategic theme

**Decision Standard:**
- Be meaning-based, not string-based
- Use conservative judgment
- Remove only when two themes are clearly the same strategic topic
- Keep both if materially different themes
- When in doubt, keep both themes

**Multi-Message Workflow:**
1. Create single thread for all messages
2. Send each theme as separate message (grouped by theme name)
3. Send trigger message: "Now that you have all X rows across Y themes, please identify and remove repetitive themes"
4. Agent processes all themes and returns deduplicated output

**Critical Output Requirements:**
- Respond ONLY with valid JSON
- NO explanations, NO markdown code fences, NO additional text
- ONLY the JSON object with keep_indices and audit

---

## Technical Stack

**Platform:** Azure AI Projects (Azure OpenAI Agents)
**Orchestration:** Python with ThreadPoolExecutor
**Authentication:** Azure Service Principal (ClientSecretCredential)
**Concurrency:** Up to 10 parallel threads for batch processing
**Data Format:** JSON between agents, CSV for final output

---

## Key Design Patterns

### 1. **Batch Processing**
Agents 2-5 split large datasets into smaller batches for parallel execution
- Agent 2: 3 themes/batch
- Agent 3: 3 themes/batch
- Agent 4: 3 themes/batch
- Agent 5: 2 themes/batch

### 2. **Thread Pooling**
Concurrent processing of batches to reduce latency
- Max 10 threads (configurable via MAX_THREADS)
- ThreadPoolExecutor with as_completed for result collection

### 3. **State Persistence**
Each agent output saved to `script_output/agent_X_output.json`
- Enables debugging and manual intervention
- Allows pipeline restart from any point

### 4. **Multi-Message Pattern**
Agent 6 uses conversational context accumulation
- Sends all themes as separate messages
- Triggers processing with final instruction
- Maintains context across messages in single thread

### 5. **Merge Strategy**
Batched results automatically merged back into unified structure
- Themes array concatenation for Agents 2-4
- Rows array concatenation for Agent 5
- Preserves all metadata (transcript_id, is_latest)

---

## Data Flow Example

```
Transcript (text)
  ↓
Agent 1 → {themes: [{theme, summary, guidance}]}
  ↓
Agent 2 → {themes: [{...theme, supporting_sentences: [...]}]}
  ↓
Agent 3 → {themes: [{...theme, subthemes: [{subtheme, supporting_sentences: [...]}]}]}
  ↓
Agent 4 → {themes: [{...theme, dimensions: [...], sub_dimensions: [...], subthemes: [...]}]}
  ↓
Agent 5 → {rows: [{transcript_id, dimension, theme, subtheme, sentence_summary, speaker, supporting_sentence, rationale, relevance_score}]}
  ↓
Agent 6 → {rows: [...], audit: [{removed_theme, kept_theme, reason}]}
```

---

## Execution Modes

### **Manual Mode**
Copy-paste outputs between agents (see `PIPELINE_INSTRUCTIONS.md`)
- Useful for testing individual agents
- Allows manual review between steps
- Enables batch splitting for large datasets

### **Automated Mode**
`multi_agent_processor.py` orchestrates entire pipeline end-to-end
- Fully automated execution
- Parallel batch processing
- Automatic result merging
- Progress logging

---

## Scalability Features

1. **Parallel Batch Processing**
   - Reduces pipeline time by ~70%
   - Configurable batch sizes per agent
   - Independent batch execution

2. **Thread Pool Management**
   - Prevents resource exhaustion
   - Configurable max threads (default: 10)
   - Graceful handling of thread failures

3. **Graceful Error Handling**
   - Per-batch logging
   - Failed batches don't block others
   - Detailed error messages with agent context

4. **Incremental Processing**
   - Agent 2 adds transcript to data
   - Each agent preserves metadata from previous steps
   - Supports multi-transcript processing

---

## File Structure

```
transcripts-agent-etl/
├── prompts/                          # Agent prompt definitions
│   ├── agent_1_theme_extraction.txt
│   ├── agent_2_supporting_sentences.txt
│   ├── agent_3_subtheme_grouping.txt
│   ├── agent_4_dimension_tagging.txt
│   ├── agent_5_table_generation.txt
│   └── agent_6_deduplication.txt
├── scripts/
│   ├── multi_agent_processor.py      # Main orchestration script
│   ├── multi_transcript_processor.py # Multi-transcript support
│   ├── config.py                     # Configuration settings
│   └── script_output/                # Agent outputs
│       ├── agent_1_output.json
│       ├── agent_2_output.json
│       ├── agent_3_output.json
│       ├── agent_4_output.json
│       ├── agent_5_output.json
│       └── agent_6_output.json
├── samples/                          # Sample data and outputs
│   ├── pfizer/
│   ├── tesla/
│   └── walmart/
├── PIPELINE_INSTRUCTIONS.md          # Manual execution guide
└── README.md                         # Project overview
```

---

## Performance Characteristics

**Single Transcript Processing:**
- Agent 1: ~30-60 seconds (depends on transcript length)
- Agent 2: ~2-5 minutes (parallel batches)
- Agent 3: ~2-4 minutes (parallel batches)
- Agent 4: ~3-5 minutes (parallel batches, complex taxonomy)
- Agent 5: ~2-3 minutes (parallel batches, scoring calculation)
- Agent 6: ~1-2 minutes (multi-message workflow)

**Total Pipeline Time:** ~10-20 minutes per transcript (with parallelization)

**Without Parallelization:** ~40-60 minutes per transcript

---

## Quality Assurance Mechanisms

1. **Evidence Exclusivity (Agent 2)**
   - Prevents duplicate quotes across themes
   - Ensures clean data for downstream analysis

2. **Subtheme Constraints (Agent 3)**
   - Max 3 subthemes per theme
   - Avoids over-fragmentation
   - Enforces meaningful clustering

3. **Dimension Guardrails (Agent 4)**
   - Anti-force-fit rules
   - Balanced judgment criteria
   - Clear company-action requirements for ESG

4. **Composite Scoring (Agent 5)**
   - Weighted relevance calculation
   - Multi-dimensional quality assessment
   - Transparent scoring methodology

5. **Conservative Deduplication (Agent 6)**
   - Meaning-based, not string-based
   - "When in doubt, keep both" principle
   - Full audit trail of removals

---

## Future Enhancements

1. **Dynamic Batch Sizing**
   - Adjust batch sizes based on theme complexity
   - Optimize for token limits and processing time

2. **Incremental Updates**
   - Process only new transcripts
   - Merge with existing analysis

3. **Quality Metrics Dashboard**
   - Track relevance score distributions
   - Monitor dimension assignment patterns
   - Identify low-quality themes

4. **Multi-Company Support**
   - Parallel processing of multiple companies
   - Cross-company theme comparison
   - Industry benchmarking

5. **Human-in-the-Loop**
   - Review interface for ambiguous themes
   - Feedback mechanism for dimension assignments
   - Continuous prompt refinement
