"""
predict.py - Entry point for VNPT AI Competition
Reads from /code/private_test.json and outputs submission.csv, submission_time.csv
"""

import json
import csv
import time
import os
from rag_langchain import LangChainRAG
from router_logic import QuestionRouter
from main import solve_question

# Initialize RAG Pipeline and Router
print("Initializing RAG pipeline and router...")
rag = LangChainRAG()
router = QuestionRouter()

# Ensure retriever is ready (loads BM25 + Vector)
rag.setup_retriever()
print("✓ RAG pipeline ready")


def predict_with_timing(test_data):
    """
    Process test data and generate submissions with timing information
    
    Args:
        test_data: List of test questions
        
    Returns:
        Tuple of (results, timings) where:
            - results: List of dicts with 'qid' and 'answer'
            - timings: List of dicts with 'qid', 'answer', and 'time'
    """
    results = []
    timings = []
    
    total_items = len(test_data)
    print(f"\nProcessing {total_items} questions...")
    print("="*80)
    
    for idx, item in enumerate(test_data, 1):
        qid = item['qid']
        
        # Measure inference time for this sample
        start_time = time.time()
        
        try:
            # Run pipeline for this question
            answer = solve_question(item)
            
            end_time = time.time()
            inference_time = end_time - start_time
            
            # Store results
            results.append({
                'qid': qid,
                'answer': answer
            })
            
            timings.append({
                'qid': qid,
                'answer': answer,
                'time': round(inference_time, 4)  # Round to 4 decimal places
            })
            
            # Progress update
            print(f"[{idx}/{total_items}] {qid}: {answer} (Time: {inference_time:.4f}s)")
            
        except Exception as e:
            print(f"[{idx}/{total_items}] {qid}: ERROR - {e}")
            # Fallback to 'A' on error
            results.append({
                'qid': qid,
                'answer': 'A'
            })
            timings.append({
                'qid': qid,
                'answer': 'A',
                'time': 0.0
            })
    
    print("="*80)
    return results, timings


def save_submission(results, output_path):
    """
    Save results to submission.csv
    
    Format:
        qid, answer
        test_0001, A
        test_0002, B
    """
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['qid', 'answer'])
        
        for result in results:
            writer.writerow([result['qid'], result['answer']])
    
    print(f"✓ Saved {len(results)} results to {output_path}")


def save_submission_with_time(timings, output_path):
    """
    Save results with timing to submission_time.csv
    
    Format:
        qid, answer, time
        test_0001, A, 1.2345
        test_0002, B, 2.9087
    """
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['qid', 'answer', 'time'])
        
        for timing in timings:
            writer.writerow([timing['qid'], timing['answer'], timing['time']])
    
    print(f"✓ Saved {len(timings)} results with timing to {output_path}")


def main():
    """
    Main entry point for prediction pipeline
    """
    # Input/output paths as specified in requirements
    input_path = '/code/private_test.json'
    output_submission = '/code/submission.csv'
    output_timing = '/code/submission_time.csv'
    
    print("="*80)
    print("VNPT AI - Prediction Pipeline")
    print("="*80)
    print(f"Input:  {input_path}")
    print(f"Output: {output_submission}")
    print(f"        {output_timing}")
    print("="*80)
    
    # Check if input file exists
    if not os.path.exists(input_path):
        print(f"✗ Error: Input file not found: {input_path}")
        print("Note: Make sure to mount the test data to /code/private_test.json")
        return
    
    # Load test data
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            test_data = json.load(f)
        print(f"✓ Loaded {len(test_data)} questions from {input_path}")
    except Exception as e:
        print(f"✗ Error loading input file: {e}")
        return
    
    # Process all questions with timing
    results, timings = predict_with_timing(test_data)
    
    # Save outputs
    save_submission(results, output_submission)
    save_submission_with_time(timings, output_timing)
    
    # Summary
    print("\n" + "="*80)
    print("✓ PREDICTION COMPLETE")
    print("="*80)
    print(f"Total questions processed: {len(results)}")
    print(f"Output files:")
    print(f"  - {output_submission}")
    print(f"  - {output_timing}")
    
    # Calculate and display total inference time
    total_time = sum(t['time'] for t in timings)
    avg_time = total_time / len(timings) if timings else 0
    print(f"\nTiming statistics:")
    print(f"  Total inference time: {total_time:.2f}s")
    print(f"  Average per question: {avg_time:.4f}s")
    print("="*80)


if __name__ == "__main__":
    main()
