"""Analysis reports (JSON / CSV / PDF). Every figure is read back from the stored results."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from fpdf import FPDF
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import queries
from app.models import AnalysisJob, ChangeFeature, ImageryAsset, Project

DISCLAIMER = ("Detections are observed differences between two images. Categories, severity and any model score are heuristic or "
              "model-inferred and require human verification; severity is not a calibrated probability.")


def _src(a: ImageryAsset | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {"id": str(a.id), "kind": a.kind, "filename": a.original_filename, "provider": a.source_provider, "product_id": a.source_product_id,
            "acquired": a.acquisition_start.isoformat() if a.acquisition_start else None, "cloud_cover_pct": a.cloud_cover_pct,
            "pixel_size_m": a.pixel_size_m, "crs_epsg": a.crs_epsg, "sha256": a.sha256}


async def build_report(db: AsyncSession, job: AnalysisJob) -> dict[str, Any]:
    F = ChangeFeature
    project = await db.get(Project, job.project_id)
    before = await db.get(ImageryAsset, job.before_asset_id) if job.before_asset_id else None
    after = await db.get(ImageryAsset, job.after_asset_id) if job.after_asset_id else None
    summary = await queries.summarize_analysis(db, job, n=15)
    top = (await db.execute(select(F).where(F.analysis_id == job.id).order_by(F.area_m2.desc()).limit(15))).scalars().all()
    reviews = {r[0]: r[1] for r in (await db.execute(select(F.review_status, func.count()).where(F.analysis_id == job.id).group_by(F.review_status))).all()}
    det = (job.processing or {}).get("detection", {})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(), "is_demo": job.is_demo,
        "data_origin": "DEMO: synthetic imagery, not real satellite data" if job.is_demo else "live",
        "analysis": {"id": str(job.id), "name": job.name, "project": project.name if project else None, "status": job.status, "input_type": job.input_type,
                     "before_date": job.before_date.isoformat() if job.before_date else None, "after_date": job.after_date.isoformat() if job.after_date else None,
                     "method": job.method, "method_reason": job.method_reason, "model_id": job.model_id, "magnitude_kind": det.get("magnitude_kind"),
                     "confidence_kind": det.get("confidence_kind"), "created_at": job.created_at.isoformat()},
        "imagery": {"before": _src(before), "after": _src(after)},
        "summary": summary.data, "headline": summary.headline, "facts": summary.facts, "reviews": reviews,
        "top_detections": [{"seq": f.seq, "id": str(f.id), "category": f.category, "category_basis": f.category_basis, "severity": f.severity, "area_m2": f.area_m2,
                            "magnitude": f.magnitude, "confidence": f.confidence, "review_status": f.review_status} for f in top],
        "processing": {"grid": (job.processing or {}).get("grid"), "timings": (job.processing or {}).get("timings"), "registration": (job.processing or {}).get("registration"),
                       "postprocess": (job.processing or {}).get("postprocess"), "config": job.config},
        "warnings": [w.get("message") for w in (job.warnings or []) if w.get("level") != "info"],
        "disclaimer": DISCLAIMER,
    }


def report_csv(rep: dict[str, Any]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    a = rep["analysis"]
    w.writerow(["section", "key", "value"])
    for k in ("name", "project", "before_date", "after_date", "method", "model_id", "status"):
        w.writerow(["analysis", k, a.get(k)])
    w.writerow(["analysis", "data_origin", rep["data_origin"]])
    s = rep["summary"]
    for k in ("feature_count", "total_changed_area_m2", "analyzed_area_m2", "unreviewed"):
        w.writerow(["summary", k, s.get(k)])
    for sev, v in s["by_severity"].items():
        w.writerow(["by_severity", sev, f"{v['count']} polygons; {v['area_m2']:.0f} m2"])
    for cat, v in s["by_category"].items():
        w.writerow(["by_category", cat, f"{v['count']} polygons; {v['area_m2']:.0f} m2"])
    w.writerow([])
    w.writerow(["seq", "category", "severity", "area_m2", "magnitude", "confidence", "review_status"])
    for d in rep["top_detections"]:
        w.writerow([d["seq"], d["category"], d["severity"], round(d["area_m2"], 1), round(d["magnitude"], 3), d["confidence"], d["review_status"]])
    return buf.getvalue().encode("utf-8")


def _ascii(s: Any) -> str:
    return str(s).encode("latin-1", "replace").decode("latin-1")


def report_pdf(rep: dict[str, Any]) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, "GeoTrace change report", new_x="LMARGIN", new_y="NEXT")
    if rep["is_demo"]:
        pdf.set_text_color(150, 60, 200)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "DEMO DATA - synthetic imagery, not real satellite data", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    a = rep["analysis"]
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _ascii(a["name"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, _ascii(f"Project: {a['project']}    Status: {a['status']}    Generated: {rep['generated_at'][:19]}Z"), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 5, _ascii(f"Imagery dates: {a['before_date'] or 'unknown'}  ->  {a['after_date'] or 'unknown'}"), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 5, _ascii(f"Method: {a['method']} ({a['method_reason']})"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    for side in ("before", "after"):
        im = rep["imagery"][side]
        if im:
            src = f"{im['provider']}:{im['product_id']}" if im["provider"] else f"{im['kind']}: {im['filename']}"
            pdf.multi_cell(0, 5, _ascii(f"{side.title()} imagery: {src} | acquired {im['acquired'] or 'unknown'} | {im['pixel_size_m']:.1f} m | EPSG:{im['crs_epsg']} | sha256 {im['sha256'][:12]}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Summary (measured)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for f in rep["facts"]:
        pdf.multi_cell(0, 5, _ascii("- " + f), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Largest detections", new_x="LMARGIN", new_y="NEXT")
    widths = [12, 52, 22, 30, 24, 24, 26]
    heads = ["#", "Category", "Severity", "Area (m2)", "Magnitude", "Score", "Review"]
    pdf.set_font("Helvetica", "B", 8)
    for w, h in zip(widths, heads):
        pdf.cell(w, 6, h, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for d in rep["top_detections"]:
        row = [d["seq"], d["category"].replace("_", " "), d["severity"], f"{d['area_m2']:,.0f}", f"{d['magnitude']:.2f}", "n/a" if d["confidence"] is None else f"{d['confidence']:.2f}", d["review_status"]]
        for w, v in zip(widths, row):
            pdf.cell(w, 6, _ascii(v), border=1)
        pdf.ln()
    if rep["warnings"]:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Quality warnings", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for w in rep["warnings"]:
            pdf.multi_cell(0, 5, _ascii("- " + w), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 4, _ascii(rep["disclaimer"]), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
