with open('app/services/onboarding_service.py', 'r') as f:
    content = f.read()

# Fix the continue_provisioning method
old = '''async def continue_provisioning(
        if not context:
            # Load from database
            prov = await provisioning_service.get_provisioning_by_org(db, organization_id)
            if not prov:
                raise ValueError("No provisioning found for organization")
            context = OnboardingContext(
                organization_id=organization_id,
                provisioning_id=prov.id,
                current_phase=OnboardingPhase.PROVISIONING_STARTED,
            )'''

new = '''async def continue_provisioning(
        self,
        db: AsyncSession,
        organization_id: str,
        caller: Any = None,
    ) -> OnboardingContext:
        """Continue provisioning after company creation.
        
        Executes the full provisioning lifecycle.
        """
        context = self._active_onboardings.get(organization_id)
        if not context:
            # Load from database
            prov = await provisioning_service.get_provisioning_by_org(db, organization_id)
            if not prov:
                raise ValueError("No provisioning found for organization")
            context = OnboardingContext(
                organization_id=organization_id,
                provisioning_id=prov.id,
                current_phase=OnboardingPhase.PROVISIONING_STARTED,
            )
            self._active_onboardings[organization_id] = context
        
        try:
            # Execute full provisioning
            provisioning = await provisioning_service.execute_provisioning(
                db,
                provisioning_id=context.provisioning_id,
                caller=caller,
            )
            
            context.current_phase = OnboardingPhase.PROVISIONING_COMPLETED
            context.completed_steps.append("provisioning_completed")
            
            # Admin is already created during organization creation
            # Get admin user/employee
            org = await db.get(Organization, context.organization_id)
            if org and org.owner_id:
                from app.people.employee_service import employee_service
                emp = await db.execute(
                    select(Employee).where(Employee.user_id == org.owner_id)
                )
                emp = emp.scalar_one_or_none()
                if emp:
                    context.admin_employee_id = emp.id
            
            context.current_phase = OnboardingPhase.ADMIN_SETUP
            context.completed_steps.append("admin_setup")
            
            # Emit completion event
            await publish_event(
                db,
                name="onboarding.completed",
                actor_id="system",
                organization_id=organization_id,
                payload={"provisioning_id": context.provisioning_id},
            )
            
            return context
        except Exception as e:
            logger.error(f"Provisioning failed for {organization_id}: {e}")
            raise

    async def get_onboarding_context(self, organization_id: str) -> Optional[OnboardingContext]:
        return self._active_onboardings.get(organization_id)


# Global instance
onboarding_service = OnboardingService()'''

content = content.replace(old, new)

with open('app/services/onboarding_service.py', 'w') as f:
    f.write(content)
print('Done')