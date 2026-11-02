import ast

code = '''
async def _check_prediction_uncalibrated(
        self,
        db: AsyncSession,
        organization_id: str,
        changed_since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[IntegrityFinding]:
        findings = []

        query = select(PredictionCalibration).where(
            PredictionCalibration.organization_id == organization_id,
            PredictionCalibration.status != "calibrated"
        )
        if changed_since:
            query = query.where(PredictionCalibration.updated_at >= changed_since)

        result = await db.execute(query.limit(limit))
        for cal in result.scalars().all():
            findings.append(IntegrityFinding(
                id=self._gen_id(),
                organization_id=organization_id,
                finding_type=IntegrityFindingType.GATE29_PREDICTION_UNCALIBRATED,
                severity=IntegritySeverity.MEDIUM,
                entity_type="PredictionCalibration",
                entity_id=cal.id,
                title="Uncalibrated prediction",
                description=f"Prediction calibration {cal.id} for {cal.prediction_type} is in status '{cal.status}'",
                observed_evidence={"calibration_id": cal.id, "prediction_type": cal.prediction_type, "status": cal.status},
                provenance={"check": "gate29_calibration", "status": cal.status},
                source_subsystem="gate29_integrity",
            ))

        return findings
'''

try:
    ast.parse(code)
    print('Valid')
except SyntaxError as e:
    print(f'Invalid: {e}')