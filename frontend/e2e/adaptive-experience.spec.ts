import { test, expect } from "@playwright/test";

test.describe("Universal Adaptive Experience Architecture", () => {
  test.beforeEach(async ({ page }) => {
    // Login and navigate to workspace
    await page.goto("/login");
    await page.fill('input[name="email"]', "test@example.com");
    await page.fill('input[name="password"]', "password123");
    await page.click('button[type="submit"]');
    await page.waitForURL("/home");
  });

  test.describe("Startup Profile (5-10 employees)", () => {
    test("shows simplified navigation for startup profile", async ({
      page,
    }) => {
      // Set experience profile to startup via API
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "startup" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace");
      await page.waitForLoadState("networkidle");

      // Check startup tabs only
      const tabs = await page
        .locator('[role="tablist"] button')
        .allTextContents();
      expect(tabs).toContain("My Day");
      expect(tabs).not.toContain("Workspace");
      expect(tabs).not.toContain("Company Home");
      expect(tabs).not.toContain("Manager");
    });

    test("shows only essential sidebar groups for startup", async ({
      page,
    }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "startup" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace");
      await page.waitForLoadState("networkidle");

      // Check sidebar groups
      const groupLabels = await page
        .locator(".text-faint.uppercase")
        .allTextContents();
      expect(groupLabels).toContain("WORKSPACE");
      expect(groupLabels).toContain("AI");
      expect(groupLabels).toContain("COMPANY");

      // Enterprise groups should not be visible
      expect(groupLabels).not.toContain("PEOPLE");
      expect(groupLabels).not.toContain("HR");
      expect(groupLabels).not.toContain("FINANCE");
      expect(groupLabels).not.toContain("ENTERPRISE");
    });

    test("workspace overview shows only My Work section for startup", async ({
      page,
    }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "startup" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace?tab=workspace");
      await page.waitForLoadState("networkidle");

      const sectionTitles = await page.locator("h3").allTextContents();
      expect(sectionTitles).toContain("My Work");
      expect(sectionTitles).not.toContain("Company Operations");
      expect(sectionTitles).not.toContain("Intelligence");
    });
  });

  test.describe("Growing Profile (11-50 employees)", () => {
    test("shows expanded navigation for growing profile", async ({ page }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "growing" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace");
      await page.waitForLoadState("networkidle");

      const tabs = await page
        .locator('[role="tablist"] button')
        .allTextContents();
      expect(tabs).toContain("My Day");
      expect(tabs).toContain("Workspace");
    });

    test("shows People, Work, Knowledge groups for growing", async ({
      page,
    }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "growing" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace");
      await page.waitForLoadState("networkidle");

      const groupLabels = await page
        .locator(".text-faint.uppercase")
        .allTextContents();
      expect(groupLabels).toContain("PEOPLE");
      expect(groupLabels).toContain("WORK");
      expect(groupLabels).toContain("KNOWLEDGE");
      expect(groupLabels).toContain("COMMUNITY");
    });

    test("workspace overview shows Company Operations and Intelligence for growing", async ({
      page,
    }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "growing" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace?tab=workspace");
      await page.waitForLoadState("networkidle");

      const sectionTitles = await page.locator("h3").allTextContents();
      expect(sectionTitles).toContain("My Work");
      expect(sectionTitles).toContain("Company Operations");
      expect(sectionTitles).toContain("Intelligence");
    });
  });

  test.describe("Enterprise Profile (5000+ employees)", () => {
    test("shows all navigation groups for enterprise", async ({ page }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "large_enterprise" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace");
      await page.waitForLoadState("networkidle");

      const groupLabels = await page
        .locator(".text-faint.uppercase")
        .allTextContents();
      expect(groupLabels).toContain("PEOPLE");
      expect(groupLabels).toContain("HR");
      expect(groupLabels).toContain("FINANCE");
      expect(groupLabels).toContain("INTELLIGENCE");
      expect(groupLabels).toContain("KNOWLEDGE");
      expect(groupLabels).toContain("GOVERNANCE");
      expect(groupLabels).toContain("PLATFORM");
      expect(groupLabels).toContain("ADMIN");
    });

    test("workspace overview shows all sections for enterprise", async ({
      page,
    }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "large_enterprise" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace?tab=workspace");
      await page.waitForLoadState("networkidle");

      const sectionTitles = await page.locator("h3").allTextContents();
      expect(sectionTitles).toContain("My Work");
      expect(sectionTitles).toContain("Company Operations");
      expect(sectionTitles).toContain("Intelligence");
    });
  });

  test.describe("Profile Transition", () => {
    test("adapts UI when profile changes from startup to growing", async ({
      page,
    }) => {
      // Start as startup
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "startup" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace");
      await page.waitForLoadState("networkidle");

      let groupLabels = await page
        .locator(".text-faint.uppercase")
        .allTextContents();
      expect(groupLabels).not.toContain("PEOPLE");

      // Transition to growing
      await page.request.post("/api/v1/company-experience/transition", {
        data: {
          new_profile: "growing",
          reason: "Company grew to 20 employees",
        },
        headers: { "Content-Type": "application/json" },
      });

      // Refresh and check
      await page.reload();
      await page.waitForLoadState("networkidle");

      groupLabels = await page
        .locator(".text-faint.uppercase")
        .allTextContents();
      expect(groupLabels).toContain("PEOPLE");
      expect(groupLabels).toContain("WORK");
    });

    test("preserves organization identity during profile transition", async ({
      page,
    }) => {
      // Get organization ID before transition
      const orgBefore = await page.request.get("/api/v1/organizations/me");
      const orgDataBefore = await orgBefore.json();
      const orgId = orgDataBefore.id;
      const orgName = orgDataBefore.name;

      // Transition through profiles
      for (const profile of ["growing", "mid_market", "large_enterprise"]) {
        await page.request.post("/api/v1/company-experience/transition", {
          data: { new_profile: profile, reason: `Transition to ${profile}` },
          headers: { "Content-Type": "application/json" },
        });
      }

      // Verify organization identity preserved
      const orgAfter = await page.request.get("/api/v1/organizations/me");
      const orgDataAfter = await orgAfter.json();
      expect(orgDataAfter.id).toBe(orgId);
      expect(orgDataAfter.name).toBe(orgName);
    });
  });

  test.describe("Company Home Adaptive Content", () => {
    test("shows simplified metrics for startup in Company Home", async ({
      page,
    }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "startup" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace?tab=company-home");
      await page.waitForLoadState("networkidle");

      // Check for simplified metrics
      const statLabels = await page
        .locator(".stat-card-label")
        .allTextContents();
      expect(statLabels).toContain("Active Objectives");
      expect(statLabels).toContain("Active Projects");
      // Financial state should not be shown for startup
      expect(statLabels).not.toContain("Revenue");
      expect(statLabels).not.toContain("Expenses");
    });

    test("shows financial state for growing companies in Company Home", async ({
      page,
    }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "growing" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace?tab=company-home");
      await page.waitForLoadState("networkidle");

      const statLabels = await page
        .locator(".stat-card-label")
        .allTextContents();
      expect(statLabels).toContain("Revenue");
      expect(statLabels).toContain("Expenses");
    });

    test("shows Digital Twin link for growing companies", async ({ page }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "growing" },
        headers: { "Content-Type": "application/json" },
      });

      await page.goto("/workspace?tab=company-home");
      await page.waitForLoadState("networkidle");

      const brainLinks = await page
        .locator('a:has-text("Explore Twin")')
        .allTextContents();
      expect(brainLinks.length).toBeGreaterThan(0);
    });
  });

  test.describe("Module Access Control", () => {
    test("finance module not accessible for startup", async ({ page }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "startup" },
        headers: { "Content-Type": "application/json" },
      });

      const response = await page.request.get(
        "/api/v1/company-experience/module-access/finance",
      );
      const data = await response.json();
      expect(data.accessible).toBe(false);
    });

    test("finance module accessible for enterprise", async ({ page }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: { experience_profile: "large_enterprise" },
        headers: { "Content-Type": "application/json" },
      });

      const response = await page.request.get(
        "/api/v1/company-experience/module-access/finance",
      );
      const data = await response.json();
      expect(data.accessible).toBe(true);
    });

    test("explicit module enable overrides profile", async ({ page }) => {
      await page.request.post("/api/v1/company-experience/config", {
        data: {
          experience_profile: "startup",
          enabled_modules: ["home", "workspace", "finance"],
        },
        headers: { "Content-Type": "application/json" },
      });

      const response = await page.request.get(
        "/api/v1/company-experience/module-access/finance",
      );
      const data = await response.json();
      expect(data.accessible).toBe(true);
    });
  });

  test.describe("Profile Resolution API", () => {
    test("returns suggested profile based on organization complexity", async ({
      page,
    }) => {
      const response = await page.request.get(
        "/api/v1/company-experience/profile",
      );
      const data = await response.json();

      expect(data).toHaveProperty("suggested_profile");
      expect(data).toHaveProperty("current_profile");
      expect(data).toHaveProperty("organization_complexity");
      expect(data).toHaveProperty("score_breakdown");
    });

    test("score breakdown includes all factors", async ({ page }) => {
      const response = await page.request.get(
        "/api/v1/company-experience/profile",
      );
      const data = await response.json();

      expect(data.score_breakdown).toHaveProperty("employee_score");
      expect(data.score_breakdown).toHaveProperty("depth_score");
      expect(data.score_breakdown).toHaveProperty("units_score");
      expect(data.score_breakdown).toHaveProperty("entities_score");
      expect(data.score_breakdown).toHaveProperty("geo_score");
      expect(data.score_breakdown).toHaveProperty("governance_score");
      expect(data.score_breakdown).toHaveProperty("workflow_score");
      expect(data.score_breakdown).toHaveProperty("total_score");
    });
  });

  test.describe("Experience Profile History", () => {
    test("records profile change history", async ({ page }) => {
      await page.request.post("/api/v1/company-experience/transition", {
        data: { new_profile: "growing", reason: "Test transition" },
        headers: { "Content-Type": "application/json" },
      });

      const response = await page.request.get(
        "/api/v1/company-experience/history",
      );
      const history = await response.json();

      expect(Array.isArray(history)).toBe(true);
      expect(history.length).toBeGreaterThan(0);
      expect(history[0]).toHaveProperty("previous_profile");
      expect(history[0]).toHaveProperty("new_profile");
      expect(history[0]).toHaveProperty("reason");
    });
  });
});
