with open('app/services/onboarding_service.py', 'r') as f:
    content = f.read()

# Find the start_company_onboarding method and replace it entirely
old = '''async def start_company_onboarding(
        async def continue_provisioning(
        self,
        db: AsyncSession,
        organization_id: str,
        caller: Any = None,
    ) -> OnboardingContext:
        """Continue provisioning after company creation.
        
        Executes the full provisioning lifecycle.
        """
        context = self._active_onboardings.get(organization_id)'''

new = '''async def start_company_onboarding(
        self,
        db: AsyncSession,
        context: OnboardingContext,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> OnboardingContext:
        """Start a new company onboarding journey.
        
        This is the main entry point for real company onboarding.
        Creates the organization and begins provisioning.
        """
        logger.info(f"Starting onboarding for {context.organization_name} ({context.domain})")
        
        # Validate inputs
        await self._validate_onboarding_inputs(db, context)
        
        # Check if organization already exists
        existing_org = await db.execute(
            select(Organization).where(Organization.slug == context.domain)
        )
        existing_org = existing_org.scalar_one_or_none()
        
        if existing_org:
            # Organization exists, use it
            org = existing_org
            logger.info(f"Using existing organization: {org.id}")
            
            # Get or create admin user
            if existing_org.owner_id:
                owner = await db.get(User, existing_org.owner_id)
            else:
                # Create admin user
                from app.schemas.auth import RegisterRequest
                register_payload = RegisterRequest(
                    organization_name=context.organization_name,
                    organization_slug=context.domain,
                    email=context.admin_email,
                    username=context.admin_email.split('@')[0],
                    full_name=context.admin_name,
                    password=context.admin_password or 'TempPass123!',
                    industry=None,
                    country='US',
                    timezone='UTC',
                    currency='USD',
                )
                created = await organization_service.create_organization_and_owner(
                    db, payload=RegisterRequest(
                        organization_name=context.organization_name,
                        organization_slug=context.domain,
                        email=context.admin_email,
                        username=context.admin_email.split('@')[0],
                        full_name=context.admin_name,
                        password=context.admin_password or 'TempPass123!',
                        industry=None,
                        country='US',
                        timezone='UTC',
                        currency='USD',
                    ), ip_address=ip_address, user_agent=user_agent
                )
                org = created["organization"]
                owner = created["owner"]
        else:
            # Phase 1: Create organization (via organization_service + auth_service)
            from app.schemas.auth import RegisterRequest
            register_payload = RegisterRequest(
                organization_name=context.organization_name,
                organization_slug=context.domain,
                email=context.admin_email,
                username=context.admin_email.split('@')[0],
                full_name=context.admin_name,
                password=context.admin_password or 'TempPass123!',
                industry=None,
                country='US',
                timezone='UTC',
                currency='USD',
            )
            created = await organization_service.create_organization_and_owner(
                db, payload=register_payload, ip_address=ip_address, user_agent=user_agent
            )
            org = created["organization"]
            owner = created["owner"]
        
        context.organization_id = org.id
        context.admin_user_id = owner.id
        context.current_phase = OnboardingPhase.PROVISIONING_STARTED
        context.completed_steps.append("company_creation")
        
        # Phase 2: Start provisioning (infrastructure setup) using existing organization
        provisioning = await provisioning_service.start_provisioning(
            db,
            organization_name=context.organization_name,
            domain=context.domain,
            admin_email=context.admin_email,
            admin_name=context.admin_name,
            plan_key=context.plan_key,
            billing_interval=context.billing_interval,
            custom_domain=context.custom_domain,
            organization_id=context.organization_id,
        )
        
        context.provisioning_id = provisioning.id
        context.current_phase = OnboardingPhase.PROVISIONING_STARTED
        context.completed_steps.append("provisioning_started")
        
        # Store context
        self._active_onboardings[org.id] = context
        
        # Emit event
        await publish_event(
            db,
            name="onboarding.started",
            actor_id="system",
            organization_id=org.id,
            payload={
                "organization_name": context.organization_name,
                "domain": context.domain,
                "plan": context.plan_key,
            },
        )
        
        await db.flush()
        logger.info(f"Onboarding started for organization {org.id}")
        
        return context

    async def continue_provisioning('''

content = content.replace(old, new)

with open('app/services/onboarding_service.py', 'w') as f:
    f.write(content)
print('Done')