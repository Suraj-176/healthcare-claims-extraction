"""
Skeleton Pass demo UI. Upload a claim page image, watch it move through the pipeline, and see
the classification, extraction, validation, and cost result live.

Run with: streamlit run ui/streamlit_app.py
"""

import json
import sys
import tempfile
from pathlib import Path

import streamlit as st
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from cost.cost_tracker import CostTracker
from pipeline import process_page

st.set_page_config(page_title="Claims Extraction Pipeline — Demo", layout="wide")
st.title("Healthcare Claims Extraction — Pipeline Demo")
st.caption("Skeleton Pass build: every stage is real and wired end-to-end; extraction accuracy "
           "improves in later depth passes.")

# Define allowed extensions (don't pass to file_uploader to avoid long display list)
ALLOWED_EXTENSIONS = {"tif", "tiff", "png", "jpg", "jpeg"} | {f"{i:03d}" for i in range(1, 100)}

st.info("📁 **Supported file types:** TIFF (.tif, .tiff, .001-.099), PNG, JPG")
uploaded = st.file_uploader("Upload a scanned claim page", type=None)

if uploaded is not None:
    # Manual extension validation
    file_ext = uploaded.name.split('.')[-1].lower()
    
    if file_ext not in ALLOWED_EXTENSIONS:
        st.error(f"❌ File type '.{file_ext}' not supported. Please upload: TIFF, PNG, JPG, or .001-.099 files.")
        st.stop()
    
    # Use system temp directory (works on Windows, Linux, macOS)
    tmp_dir = Path(tempfile.gettempdir())
    tmp_path = tmp_dir / uploaded.name
    tmp_path.write_bytes(uploaded.getvalue())

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Uploaded page")
        try:
            st.image(Image.open(tmp_path), use_container_width=True)
        except Exception:
            st.warning("Preview not available for this file type, but processing will still run.")

    with col2:
        # Header with export button on the right
        head_col1, head_col2 = st.columns([3, 1])
        with head_col1:
            st.subheader("📊 Pipeline Result")
        with head_col2:
            # Export button (will be enabled after processing)
            result_placeholder = st.empty()
        
        with st.spinner("Running preprocessing → classification → extraction → validation..."):
            tracker = CostTracker()
            result = process_page(str(tmp_path), tracker)

        # Now add export button after we have results
        with head_col2:
            result_json = json.dumps(result, indent=2, default=str)
            st.download_button(
                label="📥 Export",
                data=result_json,
                file_name=f"result_{uploaded.name}.json",
                mime="application/json",
                help="Download extraction results"
            )

        tier = result.get("classification", {}).get("tier", "n/a")
        status = result.get("final_status", "n/a")
        
        # Compact display with smaller fonts
        st.markdown("##### Processing Summary")
        
        col_a, col_b = st.columns(2)
        
        with col_a:
            # Status indicator
            status_emoji = "✅" if status == "ok" else ("⚠️" if "skipped" in status else "❌")
            st.markdown(f"**Status:** {status_emoji} **`{status}`**")
            
            # OCR confidence
            if "extraction" in result:
                confidence = result['extraction'].get('mean_confidence', 0)
                conf_emoji = "🟢" if confidence > 60 else ("🟡" if confidence > 40 else "🔴")
                st.markdown(f"**Confidence:** {conf_emoji} **`{confidence:.1f}%`**")
        
        with col_b:
            # Form type
            tier_map = {
                "tier_a": "CMS-1500",
                "tier_b": "CMS-1500+Attach", 
                "tier_c": "UB-04",
                "tier_d": "Separator",
                "unknown_layout": "Unknown"
            }
            tier_desc = tier_map.get(tier, tier)
            st.markdown(f"**Form:** **`{tier_desc}`**")
            
            # Cost with comparison
            cost = tracker.summary()['blended_cost_per_page']
            savings = ((0.050 - cost) / 0.050) * 100
            st.markdown(f"**Cost:** **`${cost:.4f}`** <span style='color:green;font-size:0.9em'>(-{savings:.0f}%)</span>", unsafe_allow_html=True)
        
        # Compact info message with smaller, bold text
        st.markdown("<p style='font-size:0.85em; padding:8px; background-color:#e3f2fd; border-radius:4px; margin-top:10px;'><strong>💡 Hybrid OCR+LLM routing optimizes accuracy and cost</strong></p>", unsafe_allow_html=True)
        
        # Expandable JSON with internal scroll (expanded by default, moderate space)
        with st.expander("🔍 Full Extraction Data", expanded=True):
            st.markdown("<style>div[data-testid='stExpander'] div[data-testid='stVerticalBlock'] {max-height: 450px; overflow-y: auto;}</style>", unsafe_allow_html=True)
            st.json(result)
else:
    st.info("Upload a page above to run it through the pipeline.")
