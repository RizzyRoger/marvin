## Objective

The AI currently takes too long to respond. Analyze the full request-processing pipeline, identify the main causes of latency, and reduce response time without significantly reducing answer quality, reliability, or functionality.

## Tasks

1. Inspect the existing implementation and identify the most important response-time bottlenecks.
    
2. Find **4–7 practical optimizations** that are relevant to this system.
    
3. Rank the optimizations by:
    
    - Expected latency reduction
        
    - Implementation effort
        
    - Risk to response quality
        
4. Implement all safe and reasonable optimizations directly in the codebase.
    
5. Test the updated system and compare its performance with the original implementation.
    

## Areas to Investigate

Consider improvements such as:

- Removing unnecessary or duplicated model calls
    
- Running independent operations concurrently
    
- Reducing prompt and conversation-context size
    
- Avoiding unnecessary tool calls, database queries, or external API requests
    
- Streaming the response as soon as tokens become available
    
- Caching reusable prompts, results, embeddings, or retrieved context
    
- Setting sensible token limits, timeouts, and retry behavior
    
- Using faster retrieval, preprocessing, or post-processing methods
    
- Simplifying inefficient loops, sequential operations, or blocking code
    
- Reusing persistent clients, sessions, and connections
    
- Selecting a faster model when appropriate
    

Do not apply an optimization merely because it appears in this list. Confirm that it is relevant to the existing implementation first.

## Model-Switching Rule

Changing the model is a valid optimization, but **do not switch models automatically**.

Before making any model change:

1. Tell me which model is currently being used.
    
2. Identify the proposed replacement.
    
3. Explain the expected speed improvement.
    
4. Explain the likely quality, cost, context-window, and capability trade-offs.
    
5. Wait for my approval before implementing the change.
    

Continue implementing optimizations that do not require a model change while awaiting approval.

## Implementation Requirements

- Make actual code changes rather than only giving recommendations.
    
- Preserve the current behavior and user-facing features unless a change is necessary for performance.
    
- Avoid lowering output quality solely to improve benchmark results.
    
- Do not expose private reasoning or hidden chain-of-thought.
    
- Add concise comments for performance-related changes that may not be obvious.
    
- Avoid introducing unnecessary dependencies.
    
- Handle failures, timeouts, and partial results gracefully.
    
- Keep changes focused and avoid unrelated refactoring.
    
- Do not claim an improvement unless it is supported by measurements or clearly identified as an estimate.
    

## Performance Measurement

Measure the system before and after the changes using the same representative prompts. Where possible, report:

- Time to first token
    
- Total response time
    
- Number of model calls
    
- Number of tool or external API calls
    
- Input and output token counts
    
- Retrieval or database-query time
    
- Preprocessing and post-processing time
    
- Cache-hit behavior
    
- Error and timeout rates
    

Run multiple trials when practical so that one unusually fast or slow request does not distort the results.

## Required Output

Provide the results in this order:

### 1. Baseline

Describe the current response flow and its measured or estimated latency.

### 2. Bottlenecks

Identify the specific parts of the implementation causing delays, with references to the relevant files or functions.

### 3. Selected Optimizations

List **4–7 optimizations** and explain why each one was selected.

### 4. Implementation

Apply the approved changes and summarize what was modified.

### 5. Verification

Run relevant tests and confirm that existing functionality still works.

### 6. Performance Comparison

Show before-and-after results for each available performance metric.

### 7. Remaining Opportunities

Describe any additional improvements that were not implemented, including model switching where relevant.

## Success Criteria

The task is complete when:

- At least four relevant optimizations have been identified.
    
- Safe non-model optimizations have been implemented.
    
- Any model switch has been proposed before being performed.
    
- Existing functionality continues to work.
    
- Response-time improvements have been measured or clearly estimated.
    
- The final report explains exactly what changed and what impact it had.