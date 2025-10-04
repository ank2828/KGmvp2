import { PipedreamClient } from "@pipedream/sdk/server";
import * as dotenv from "dotenv";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";

// Get __dirname equivalent in ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Load environment variables from .env.local
dotenv.config({ path: resolve(__dirname, "../.env.local") });

async function discoverTriggers() {
  const {
    NEXT_PUBLIC_PIPEDREAM_PROJECT_ID,
    PIPEDREAM_CLIENT_ID,
    PIPEDREAM_CLIENT_SECRET,
    PIPEDREAM_PROJECT_ENVIRONMENT,
  } = process.env;

  if (!PIPEDREAM_CLIENT_ID || !PIPEDREAM_CLIENT_SECRET || !NEXT_PUBLIC_PIPEDREAM_PROJECT_ID) {
    throw new Error("Missing required Pipedream credentials in environment");
  }

  const client = new PipedreamClient({
    projectId: NEXT_PUBLIC_PIPEDREAM_PROJECT_ID,
    projectEnvironment: (PIPEDREAM_PROJECT_ENVIRONMENT as "development" | "production") || "production",
    clientId: PIPEDREAM_CLIENT_ID,
    clientSecret: PIPEDREAM_CLIENT_SECRET,
  });

  console.log("\n=== DISCOVERING PIPEDREAM TRIGGERS ===\n");

  // Gmail triggers
  console.log("📧 GMAIL TRIGGERS:");
  console.log("-".repeat(80));

  try {
    // First, try listing all Gmail triggers
    const allGmailTriggers = await client.triggers.list({
      app: "gmail"
    });
    console.log(`\nAll Gmail triggers (${allGmailTriggers.data.length} total):`);
    allGmailTriggers.data.forEach((trigger: any) => {
      console.log(`  - ID: ${trigger.id}`);
      console.log(`    Name: ${trigger.name}`);
      console.log(`    Key: ${trigger.key}`);
      console.log(`    Description: ${trigger.description}`);
      console.log(`    Type: ${trigger.type || "N/A"}`);
      console.log("");
    });

    // Then search for specific keywords
    const gmailNewEmail = await client.triggers.list({
      app: "gmail",
      q: "new email"
    });
    console.log(`\nSearch: 'new email' (${gmailNewEmail.data.length} results):`);
    gmailNewEmail.data.forEach((trigger: any) => {
      console.log(`  - ${trigger.name} (${trigger.key})`);
    });

    const gmailInstant = await client.triggers.list({
      app: "gmail",
      q: "instant"
    });
    console.log(`\nSearch: 'instant' (${gmailInstant.data.length} results):`);
    gmailInstant.data.forEach((trigger: any) => {
      console.log(`  - ${trigger.name} (${trigger.key})`);
    });
  } catch (error) {
    console.error("Error fetching Gmail triggers:", error);
  }

  // Google Drive triggers
  console.log("\n📁 GOOGLE DRIVE TRIGGERS:");
  console.log("-".repeat(80));

  try {
    // First, try listing all Google Drive triggers
    const allDriveTriggers = await client.triggers.list({
      app: "google_drive"
    });
    console.log(`\nAll Google Drive triggers (${allDriveTriggers.data.length} total):`);
    allDriveTriggers.data.forEach((trigger: any) => {
      console.log(`  - ID: ${trigger.id}`);
      console.log(`    Name: ${trigger.name}`);
      console.log(`    Key: ${trigger.key}`);
      console.log(`    Description: ${trigger.description}`);
      console.log(`    Type: ${trigger.type || "N/A"}`);
      console.log("");
    });

    const driveNewFile = await client.triggers.list({
      app: "google_drive",
      q: "new file"
    });
    console.log(`\nSearch: 'new file' (${driveNewFile.data.length} results):`);
    driveNewFile.data.forEach((trigger: any) => {
      console.log(`  - ${trigger.name} (${trigger.key})`);
    });
  } catch (error) {
    console.error("Error fetching Google Drive triggers:", error);
  }

  // HubSpot triggers
  console.log("\n🔄 HUBSPOT TRIGGERS:");
  console.log("-".repeat(80));

  try {
    // First, try listing all HubSpot triggers
    const allHubspotTriggers = await client.triggers.list({
      app: "hubspot"
    });
    console.log(`\nAll HubSpot triggers (${allHubspotTriggers.data.length} total):`);
    allHubspotTriggers.data.forEach((trigger: any) => {
      console.log(`  - ID: ${trigger.id}`);
      console.log(`    Name: ${trigger.name}`);
      console.log(`    Key: ${trigger.key}`);
      console.log(`    Description: ${trigger.description}`);
      console.log(`    Type: ${trigger.type || "N/A"}`);
      console.log("");
    });

    const hubspotContact = await client.triggers.list({
      app: "hubspot",
      q: "contact"
    });
    console.log(`\nSearch: 'contact' (${hubspotContact.data.length} results):`);
    hubspotContact.data.forEach((trigger: any) => {
      console.log(`  - ${trigger.name} (${trigger.key})`);
    });
  } catch (error) {
    console.error("Error fetching HubSpot triggers:", error);
  }

  console.log("\n=== DISCOVERY COMPLETE ===\n");
}

discoverTriggers().catch(console.error);
