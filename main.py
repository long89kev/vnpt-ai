import json
import csv
import re
import os
from rag_langchain import LangChainRAG
from prompt_templates import (
    construct_prompt, construct_batch_prompt,
    SYSTEM_PROMPTS, BATCH_SYSTEM_PROMPT
)
from get_response import get_response
from get_embedding import get_embedding
from router_logic import QuestionRouter

# Initialize RAG Pipeline and Router
rag = LangChainRAG()
router = QuestionRouter()

# Ensure retriever is ready (loads BM25 + Vector)
rag.setup_retriever()


def solve_question(item):
    """
    Solve a single question with domain-aware routing
    """
    question_text = item['question']
    choices = item['choices']
    
    # 1. Classify question into domain
    domain, confidence = router.classify_question(question_text, choices)
    strategy = router.get_strategy_config(domain)
    
    # 2. Get context based on domain strategy
    context = ""
    if "Đoạn thông tin" in question_text:
        # Extract context from question (RAG domain)
        parts = question_text.split("Câu hỏi:")
        if len(parts) > 1:
            context = parts[0].strip()
            question_text = parts[-1].strip()
    elif strategy['use_rag'] and strategy['top_k_docs'] > 0:
        # Use RAG retrieval for other domains if configured
        retrieved_docs = rag.query(question_text)
        # Limit to top_k_docs if needed
        retrieved_docs = retrieved_docs[:strategy['top_k_docs']]
        context = "\n\n".join([doc.page_content for doc in retrieved_docs])
    
    # 3. Construct domain-specific prompt
    prompt = construct_prompt(question_text, choices, context, domain.lower())
    
    # 4. Call LLM with domain-specific system prompt
    system_prompt = SYSTEM_PROMPTS.get(
        domain.lower(), 
        SYSTEM_PROMPTS["multidomain"]
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    
    try:
        raw_answer = get_response(
            messages,
            model=strategy.get('model', 'small'),
            temperature=strategy.get('temperature', 0.3)
        )
    except Exception as e:
        print(f"Error calling LLM for {domain}: {e}")
        raw_answer = ""
    
    # 5. Post-process answer (Extract A, B, C, D...)
    # Get number of choices to validate
    num_choices = len(choices)
    max_valid_letter = chr(ord('A') + num_choices - 1)  # A + 0 = A, A + 5 = F, etc.
    
    # Try to find answer markers with dots or colons first
    answer_pattern = r'(?:^|\s|[Đđ]áp án|[Cc]họn|[Tt]rả lời|[Kk]ết quả)\s*[:\-]?\s*([A-Z])(?:[.\s]|$)'
    match = re.search(answer_pattern, raw_answer, re.IGNORECASE)
    
    if match:
        answer = match.group(1).upper()
    else:
        # Fallback 1: find single letter at start of line
        match = re.search(r'^([A-Z])$', raw_answer.strip(), re.MULTILINE)
        if match:
            answer = match.group(1).upper()
        else:
            # Fallback 2: find standalone letter
            match = re.search(r'\b([A-Z])\b', raw_answer)
            answer = match.group(1).upper() if match else "A"
    
    # Validate: answer must be within valid range for this question
    if answer not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        print(f"  Warning: Invalid answer '{answer}' (not a letter), defaulting to A")
        answer = "A"
    elif ord(answer) > ord(max_valid_letter):
        print(f"  Warning: Answer '{answer}' exceeds choices (max={max_valid_letter}), defaulting to A")
        answer = "A"
    
    # Debug info
    print(f"  Domain: {domain} (conf: {confidence:.2f}) | Choices: {num_choices} (A-{max_valid_letter}) | Raw: '{raw_answer[:30]}...' -> {answer}")
    
    return answer

def process_domain_batch(domain_items, domain):
    """
    Process a single domain batch (up to 10 questions)
    Returns dict of {qid: answer}
    """
    strategy = router.get_strategy_config(domain)
    
    # Prepare items for this domain
    prepared_items = []
    for item in domain_items:
        question_text = item['question']
        choices = item['choices']
        
        # Get context based on domain strategy
        context = ""
        if "Đoạn thông tin" in question_text:
            parts = question_text.split("Câu hỏi:")
            if len(parts) > 1:
                context = parts[0].strip()
                question_text = parts[-1].strip()
        elif strategy['use_rag'] and strategy['top_k_docs'] > 0:
            retrieved_docs = rag.query(question_text)
            retrieved_docs = retrieved_docs[:strategy['top_k_docs']]
            context = "\n\n".join([doc.page_content for doc in retrieved_docs])
            
        prepared_items.append({
            'question': question_text,
            'choices': choices,
            'context': context,
            'qid': item['qid']
        })
    
    # Construct domain-specific batch prompt
    prompt = construct_batch_prompt(prepared_items)
    
    # Get domain-specific system prompt
    from prompt_templates import BATCH_SYSTEM_PROMPTS
    system_prompt = BATCH_SYSTEM_PROMPTS.get(
        domain.lower(),
        BATCH_SYSTEM_PROMPTS["multidomain"]
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    
    # Call LLM with domain-specific model and temperature
    answers = {}
    for attempt in range(2):
        try:
            raw_answer = get_response(
                messages,
                model=strategy.get('model', 'small'),
                temperature=strategy.get('temperature', 0.3)
            )
            raw_answer = raw_answer.replace("```json", "").replace("```", "").strip()
            answers = json.loads(raw_answer)
            print(f"  ✓ {domain} batch ({len(domain_items)} questions) processed")
            break
        except Exception as e:
            print(f"  ✗ Attempt {attempt + 1} failed: {e}")
            if attempt == 1:
                # Fallback to individual solving
                print(f"  → Falling back to individual solving...")
                for i, original_item in enumerate(domain_items, 1):
                    try:
                        ans = solve_question(original_item)
                        answers[str(i)] = ans
                    except Exception as inner_e:
                        print(f"    Error on {original_item.get('qid')}: {inner_e}")
                        answers[str(i)] = "A"
    
    # Map answers to QIDs
    results = {}
    for i, item in enumerate(prepared_items, 1):
        ans = answers.get(str(i), "A")
        if not ans or ans not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            ans = "A"
        results[item['qid']] = ans
    
    return results

def solve_batch(items):
    """
    Solve a batch of questions with domain-aware streaming batching
    All domains: Batch when reaching batch_size questions
    """
    from config import BATCH_CONFIG
    
    # Domain buffers to accumulate questions
    domain_buffers = {
        "PRECISION_CRITICAL": [],
        "COMPULSORY": [],
        "RAG": [],
        "STEM": [],
        "MULTIDOMAIN": []
    }
    
    all_results = {}
    batch_size = BATCH_CONFIG['batch_size']  # Default 5
    
    print(f"Processing {len(items)} questions with streaming domain batching...")
    print(f"Batch size: {batch_size} questions per domain\n")
    
    # Process items one by one, classify and group
    for idx, item in enumerate(items, 1):
        # Classify into domain
        domain, confidence = router.classify_question(item['question'], item['choices'])
        
        # Add to domain buffer
        domain_buffers[domain].append(item)
        
        # Check if this domain buffer is full
        if len(domain_buffers[domain]) >= batch_size:
            print(f"[{idx}/{len(items)}] {domain} buffer full ({batch_size} questions), processing batch...")
            
            # Process this domain batch
            batch_to_process = domain_buffers[domain][:batch_size]
            batch_results = process_domain_batch(batch_to_process, domain)
            all_results.update(batch_results)
            
            # Reset buffer for this domain
            domain_buffers[domain] = []
    
    # Process remaining items in buffers
    print(f"\n[{len(items)}/{len(items)}] Processing remaining questions...")
    for domain, remaining_items in domain_buffers.items():
        if remaining_items:
            print(f"  {domain}: {len(remaining_items)} questions remaining")
            batch_results = process_domain_batch(remaining_items, domain)
            all_results.update(batch_results)
    
    return all_results


def main():
    # Example usage with val.json
    input_path = 'data/test.json'
    output_path = 'output.csv'
    # input_path = 'data/val.json'
    # output_path = 'val.csv'
    # input_path = 'data/stem_val.json'
    # output_path = 'stem_val.csv'
    # input_path = 'data/test_stem.json'
    # output_path = 'test_stem.csv'
    
    if os.path.exists(input_path):
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Open CSV file for writing
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['qid', 'answer'])

            # Process all data in one streaming pass
            print(f"\nProcessing {len(data)} questions with streaming batching...")
            print("="*80)
            
            results = solve_batch(data)
            
            # Write results
            print("\nWriting results...")
            for qid in [item['qid'] for item in data]:
                if qid in results:
                    writer.writerow([qid, results[qid]])
                else:
                    print(f"Warning: Missing result for {qid}")
                    writer.writerow([qid, 'A'])
            
            f.flush()
            print(f"\nCompleted! Results written to {output_path}")

if __name__ == "__main__":
    main()