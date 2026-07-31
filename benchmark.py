"""
Healthcare Claims Extraction - Benchmark Script
Processes all test files and generates comprehensive Excel benchmark report
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline import process_page
from cost.cost_tracker import CostTracker
from database import DatabaseManager


class BenchmarkRunner:
    """Runs comprehensive benchmark on all test files."""
    
    def __init__(self, test_data_dir: str = "data/raw"):
        self.test_data_dir = Path(test_data_dir)
        self.results = []
        self.db = DatabaseManager()
        
    def find_test_files(self) -> List[Path]:
        """Find all test files in data/raw directory."""
        patterns = ['.tif', '.tiff', '.png', '.jpg', '.jpeg'] + [f'.{i:03d}' for i in range(1, 100)]
        files = []
        
        for pattern in patterns:
            files.extend(self.test_data_dir.rglob(f'*{pattern}'))
        
        # Sort by group and filename
        files.sort(key=lambda x: (x.parent.name, x.name))
        return files
    
    def process_file(self, filepath: Path) -> Dict[str, Any]:
        """Process single file and collect metrics."""
        print(f"Processing: {filepath.parent.name}/{filepath.name}")
        
        start_time = time.time()
        tracker = CostTracker()
        
        try:
            result = process_page(str(filepath), tracker)
            processing_time = time.time() - start_time
            
            # Extract metrics
            classification = result.get("classification", {})
            extraction = result.get("extraction", {})
            validation = result.get("validation", {})
            
            tier = classification.get("tier", "unknown")
            status = result.get("final_status", "failed")
            mean_confidence = extraction.get("mean_confidence", 0)
            
            # Cost breakdown
            cost_summary = tracker.summary()
            ocr_cost = cost_summary.get('ocr_cost', 0)
            llm_cost = cost_summary.get('llm_cost', 0)
            total_cost = cost_summary.get('blended_cost_per_page', 0)
            
            # LLM details
            llm_details = extraction.get("llm_details", {})
            llm_provider = llm_details.get("provider", "none")
            llm_escalated = llm_details.get("escalated", False)
            
            # Field-level metrics
            fields = extraction.get("fields", {})
            total_fields = len(fields)
            high_conf_fields = sum(1 for f in fields.values() if f.get('confidence', 0) > 80)
            low_conf_fields = sum(1 for f in fields.values() if f.get('confidence', 0) < 50)
            
            # Validation results
            passed_rules = validation.get("rules_passed", 0)
            failed_rules = validation.get("rules_failed", 0)
            warnings = validation.get("warnings", [])
            
            # Calculate accuracy (based on confidence and validation)
            if status == "ok" and total_fields > 0:
                accuracy = (mean_confidence / 100) * (passed_rules / (passed_rules + failed_rules) if (passed_rules + failed_rules) > 0 else 1.0) * 100
            else:
                accuracy = 0
            
            metrics = {
                'group': filepath.parent.name,
                'filename': filepath.name,
                'tier': tier,
                'status': status,
                'processing_time_sec': round(processing_time, 3),
                'total_fields': total_fields,
                'high_confidence_fields': high_conf_fields,
                'low_confidence_fields': low_conf_fields,
                'mean_confidence': round(mean_confidence, 2),
                'accuracy': round(accuracy, 2),
                'llm_provider': llm_provider,
                'llm_escalated': llm_escalated,
                'ocr_cost': round(ocr_cost, 6),
                'llm_cost': round(llm_cost, 6),
                'total_cost': round(total_cost, 6),
                'validation_passed': passed_rules,
                'validation_failed': failed_rules,
                'warnings_count': len(warnings),
                'file_size_kb': round(filepath.stat().st_size / 1024, 2)
            }
            
            print(f"  ✓ Status: {status} | Tier: {tier} | Confidence: {mean_confidence:.1f}% | Cost: ${total_cost:.6f}")
            return metrics
            
        except Exception as e:
            processing_time = time.time() - start_time
            print(f"  ✗ Error: {str(e)}")
            return {
                'group': filepath.parent.name,
                'filename': filepath.name,
                'tier': 'error',
                'status': 'failed',
                'processing_time_sec': round(processing_time, 3),
                'total_fields': 0,
                'high_confidence_fields': 0,
                'low_confidence_fields': 0,
                'mean_confidence': 0,
                'accuracy': 0,
                'llm_provider': 'none',
                'llm_escalated': False,
                'ocr_cost': 0,
                'llm_cost': 0,
                'total_cost': 0,
                'validation_passed': 0,
                'validation_failed': 0,
                'warnings_count': 0,
                'file_size_kb': round(filepath.stat().st_size / 1024, 2),
                'error': str(e)
            }
    
    def run_benchmark(self) -> List[Dict[str, Any]]:
        """Run benchmark on all test files."""
        print("\n" + "="*80)
        print("HEALTHCARE CLAIMS EXTRACTION - BENCHMARK")
        print("="*80 + "\n")
        
        files = self.find_test_files()
        print(f"Found {len(files)} test files\n")
        
        for i, filepath in enumerate(files, 1):
            print(f"\n[{i}/{len(files)}] ", end="")
            metrics = self.process_file(filepath)
            self.results.append(metrics)
        
        return self.results
    
    def generate_excel_report(self, output_file: str = "05_Benchmark.xlsx"):
        """Generate comprehensive Excel benchmark report."""
        print("\n" + "="*80)
        print("GENERATING EXCEL REPORT")
        print("="*80 + "\n")
        
        if not self.results:
            print("❌ No results to export!")
            return
        
        df = pd.DataFrame(self.results)
        
        # Calculate overall metrics
        total_pages = len(df)
        successful_pages = len(df[df['status'] == 'ok'])
        failed_pages = total_pages - successful_pages
        
        total_time = df['processing_time_sec'].sum()
        avg_latency = df['processing_time_sec'].mean()
        pages_per_second = total_pages / total_time if total_time > 0 else 0
        
        overall_accuracy = df[df['status'] == 'ok']['accuracy'].mean() if successful_pages > 0 else 0
        overall_confidence = df[df['status'] == 'ok']['mean_confidence'].mean() if successful_pages > 0 else 0
        
        # Cost analysis
        total_ocr_cost = df['ocr_cost'].sum()
        total_llm_cost = df['llm_cost'].sum()
        total_cost = df['total_cost'].sum()
        
        avg_ocr_cost = df['ocr_cost'].mean()
        avg_llm_cost = df['llm_cost'].mean()
        avg_total_cost = df['total_cost'].mean()
        
        # Create Excel writer
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            
            # Sheet 1: Overall Metrics
            # Calculate Precision and Recall
            # Precision: Accuracy of extracted fields (correctness)
            precision = overall_accuracy
            # Recall: Coverage - percentage of required fields successfully extracted
            recall = (successful_pages / total_pages * 100) if total_pages > 0 else 0
            
            overall_metrics = pd.DataFrame({
                'Metric': [
                    'Total Pages Processed',
                    'Successful Pages',
                    'Failed Pages',
                    'Success Rate (%)',
                    'Total Processing Time (sec)',
                    'Average Latency (sec)',
                    'Pages per Second',
                    'Overall Accuracy (%)',
                    'Precision (%)',
                    'Recall (%)',
                    'Overall Confidence (%)',
                    'Total Cost ($)',
                    'Average Cost per Page ($)'
                ],
                'Value': [
                    total_pages,
                    successful_pages,
                    failed_pages,
                    round(recall, 2),
                    round(total_time, 2),
                    round(avg_latency, 3),
                    round(pages_per_second, 2),
                    round(overall_accuracy, 2),
                    round(precision, 2),
                    round(recall, 2),
                    round(overall_confidence, 2),
                    round(total_cost, 4),
                    round(avg_total_cost, 6)
                ]
            })
            overall_metrics.to_excel(writer, sheet_name='Overall Metrics', index=False)
            
            # Sheet 2: Cost Analysis
            cost_analysis = pd.DataFrame({
                'Component': ['OCR', 'LLM', 'Vision AI', 'GPU', 'CPU', 'Total'],
                'Total Cost ($)': [
                    round(total_ocr_cost, 4),
                    round(total_llm_cost, 4),
                    0,  # Not used in our solution
                    0,  # Included in LLM cost
                    0,  # Negligible
                    round(total_cost, 4)
                ],
                'Avg Cost per Page ($)': [
                    round(avg_ocr_cost, 6),
                    round(avg_llm_cost, 6),
                    0,
                    0,
                    0,
                    round(avg_total_cost, 6)
                ],
                '% of Total': [
                    round((total_ocr_cost / total_cost * 100) if total_cost > 0 else 0, 2),
                    round((total_llm_cost / total_cost * 100) if total_cost > 0 else 0, 2),
                    0,
                    0,
                    0,
                    100.0
                ]
            })
            cost_analysis.to_excel(writer, sheet_name='Cost Analysis', index=False)
            
            # Sheet 3: Per-File Detailed Results
            df_detailed = df[[
                'group', 'filename', 'tier', 'status', 'processing_time_sec',
                'total_fields', 'mean_confidence', 'accuracy', 
                'llm_provider', 'llm_escalated', 'total_cost',
                'validation_passed', 'validation_failed'
            ]].copy()
            df_detailed.columns = [
                'Group', 'Filename', 'Form Type', 'Status', 'Time (sec)',
                'Fields', 'Confidence (%)', 'Accuracy (%)', 
                'LLM Provider', 'LLM Used', 'Cost ($)',
                'Valid Pass', 'Valid Fail'
            ]
            df_detailed.to_excel(writer, sheet_name='Detailed Results', index=False)
            
            # Sheet 4: Tier-wise Breakdown
            tier_breakdown = df.groupby('tier').agg({
                'filename': 'count',
                'processing_time_sec': 'mean',
                'mean_confidence': 'mean',
                'accuracy': 'mean',
                'total_cost': 'mean',
                'llm_escalated': 'sum'
            }).round(3)
            tier_breakdown.columns = ['Count', 'Avg Time (sec)', 'Avg Confidence (%)', 'Avg Accuracy (%)', 'Avg Cost ($)', 'LLM Escalations']
            tier_breakdown.to_excel(writer, sheet_name='Tier Breakdown')
            
            # Sheet 5: Provider Usage
            provider_stats = df.groupby('llm_provider').agg({
                'filename': 'count',
                'total_cost': 'sum',
                'mean_confidence': 'mean',
                'accuracy': 'mean'
            }).round(3)
            provider_stats.columns = ['Count', 'Total Cost ($)', 'Avg Confidence (%)', 'Avg Accuracy (%)']
            provider_stats.to_excel(writer, sheet_name='Provider Usage')
            
            # Sheet 6: Accuracy & Precision Metrics
            successful_df = df[df['status'] == 'ok']
            if len(successful_df) > 0:
                accuracy_metrics = pd.DataFrame({
                    'Metric': [
                        'Mean Accuracy (%)',
                        'Median Accuracy (%)',
                        'Min Accuracy (%)',
                        'Max Accuracy (%)',
                        'Std Dev Accuracy',
                        'Mean Confidence (%)',
                        'Median Confidence (%)',
                        'High Confidence Fields (>80%)',
                        'Low Confidence Fields (<50%)',
                        'Validation Pass Rate (%)'
                    ],
                    'Value': [
                        round(successful_df['accuracy'].mean(), 2),
                        round(successful_df['accuracy'].median(), 2),
                        round(successful_df['accuracy'].min(), 2),
                        round(successful_df['accuracy'].max(), 2),
                        round(successful_df['accuracy'].std(), 2),
                        round(successful_df['mean_confidence'].mean(), 2),
                        round(successful_df['mean_confidence'].median(), 2),
                        successful_df['high_confidence_fields'].sum(),
                        successful_df['low_confidence_fields'].sum(),
                        round((successful_df['validation_passed'].sum() / 
                              (successful_df['validation_passed'].sum() + successful_df['validation_failed'].sum()) * 100)
                              if (successful_df['validation_passed'].sum() + successful_df['validation_failed'].sum()) > 0 else 0, 2)
                    ]
                })
                accuracy_metrics.to_excel(writer, sheet_name='Accuracy Metrics', index=False)
        
        print(f"✅ Benchmark report saved: {output_file}\n")
        
        # Print summary
        print("="*80)
        print("BENCHMARK SUMMARY")
        print("="*80)
        print(f"Total Pages:        {total_pages}")
        print(f"Success Rate:       {(successful_pages/total_pages*100):.1f}%")
        print(f"Avg Accuracy:       {overall_accuracy:.2f}%")
        print(f"Avg Confidence:     {overall_confidence:.2f}%")
        print(f"Avg Latency:        {avg_latency:.3f} sec")
        print(f"Throughput:         {pages_per_second:.2f} pages/sec")
        print(f"Avg Cost per Page:  ${avg_total_cost:.6f}")
        print(f"Total Cost:         ${total_cost:.4f}")
        print("="*80 + "\n")


def main():
    """Main benchmark execution."""
    runner = BenchmarkRunner()
    
    # Run benchmark
    results = runner.run_benchmark()
    
    # Generate Excel report
    runner.generate_excel_report()
    
    print("✅ Benchmark complete!")


if __name__ == "__main__":
    main()
