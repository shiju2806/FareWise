"""Export service — PDF and CSV generation for reports."""

import io
import logging
import uuid
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.policy import SavingsReport
from app.models.trip import Trip
from app.models.user import User

logger = logging.getLogger(__name__)


class ExportService:
    """Generates PDF and CSV reports."""

    async def generate_savings_pdf(self, db: AsyncSession, trip_id: uuid.UUID) -> bytes:
        """Generate a savings report PDF for a trip."""
        result = await db.execute(
            select(Trip).where(Trip.id == trip_id).options(selectinload(Trip.legs))
        )
        trip = result.scalar_one_or_none()
        if not trip:
            raise ValueError("Trip not found")

        traveler_result = await db.execute(select(User).where(User.id == trip.traveler_id))
        traveler = traveler_result.scalar_one_or_none()

        sr_result = await db.execute(
            select(SavingsReport).where(SavingsReport.trip_id == trip_id)
        )
        sr = sr_result.scalar_one_or_none()

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5 * inch)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        elements.append(Paragraph("FareWise Savings Report", styles["Title"]))
        elements.append(Spacer(1, 12))

        # Trip info
        traveler_name = f"{traveler.first_name} {traveler.last_name}" if traveler else "Unknown"
        info = [
            f"<b>Trip:</b> {trip.title or 'Untitled'}",
            f"<b>Traveler:</b> {traveler_name}",
            f"<b>Status:</b> {trip.status}",
            f"<b>Generated:</b> {date.today().isoformat()}",
        ]
        for line in info:
            elements.append(Paragraph(line, styles["Normal"]))
        elements.append(Spacer(1, 12))

        # Legs table
        if trip.legs:
            elements.append(Paragraph("<b>Itinerary</b>", styles["Heading2"]))
            leg_data = [["Route", "Date", "Cabin"]]
            for leg in trip.legs:
                leg_data.append([
                    f"{leg.origin_airport} -> {leg.destination_airport}",
                    str(leg.preferred_date),
                    leg.cabin_class,
                ])
            table = Table(leg_data, colWidths=[3 * inch, 1.5 * inch, 1.5 * inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 12))

        # Savings
        if sr:
            elements.append(Paragraph("<b>Cost Analysis</b>", styles["Heading2"]))
            cost_data = [
                ["Metric", "Amount (CAD)"],
                ["Selected Total", f"${float(sr.selected_total):,.2f}"],
                ["Cheapest Available", f"${float(sr.cheapest_total):,.2f}"],
                ["Most Expensive", f"${float(sr.most_expensive_total):,.2f}"],
                ["Savings vs Expensive", f"${float(sr.savings_vs_expensive):,.2f}"],
                ["Policy Status", sr.policy_status or "N/A"],
            ]
            table = Table(cost_data, colWidths=[3 * inch, 3 * inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 12))

            if sr.narrative:
                elements.append(Paragraph("<b>Summary</b>", styles["Heading2"]))
                elements.append(Paragraph(sr.narrative, styles["Normal"]))

        doc.build(elements)
        return buf.getvalue()

    async def generate_audit_pdf(self, db: AsyncSession, trip_id: uuid.UUID, timeline: list[dict]) -> bytes:
        """Generate an audit trail PDF."""
        result = await db.execute(select(Trip).where(Trip.id == trip_id))
        trip = result.scalar_one_or_none()
        if not trip:
            raise ValueError("Trip not found")

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5 * inch)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("FareWise Audit Trail", styles["Title"]))
        elements.append(Paragraph(f"Trip: {trip.title or 'Untitled'}", styles["Normal"]))
        elements.append(Paragraph(f"Generated: {date.today().isoformat()}", styles["Normal"]))
        elements.append(Spacer(1, 12))

        # Timeline table
        if timeline:
            data = [["Time", "Event", "Actor", "Details"]]
            for entry in timeline:
                details = ""
                if isinstance(entry.get("details"), dict):
                    details = ", ".join(
                        f"{k}: {v}" for k, v in entry["details"].items() if v is not None
                    )
                data.append([
                    entry.get("timestamp", "")[:19],
                    entry.get("event", ""),
                    entry.get("actor", ""),
                    details[:80],
                ])

            table = Table(data, colWidths=[1.5 * inch, 1.2 * inch, 1.2 * inch, 2.1 * inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            elements.append(table)

        doc.build(elements)
        return buf.getvalue()


export_service = ExportService()
