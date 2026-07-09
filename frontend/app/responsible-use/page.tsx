// specs/04-tasks/task-19-moderation-consent.md: "short 'responsible use'
// page". Static - no interactivity, no auth required (linked from the
// enrollment flows so it's readable before the user commits to anything).
import Link from "next/link";

export default function ResponsibleUsePage() {
  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: "4rem 1.5rem" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>Responsible use</h1>
      <p style={{ color: "var(--text-dim)", marginTop: "1rem", lineHeight: 1.6 }}>
        This is a private, invite-only site for 1–2 known users making videos of themselves,
        in their own voice. It exists to help you make videos as yourself — not as anyone else.
      </p>

      <h2 style={{ fontSize: "1.05rem", fontWeight: 600, marginTop: "2rem" }}>Your own likeness only</h2>
      <p style={{ color: "var(--text-dim)", marginTop: "0.5rem", lineHeight: 1.6 }}>
        Every selfie and voice recording you upload must be your own. Uploading is only
        possible after explicitly confirming this — that confirmation, with a timestamp, is
        recorded against the artifact it applies to. You can delete any selfie, portrait, or
        voice sample at any time, which removes the file and its embedding.
      </p>

      <h2 style={{ fontSize: "1.05rem", fontWeight: 600, marginTop: "2rem" }}>Personas, not impersonation</h2>
      <p style={{ color: "var(--text-dim)", marginTop: "0.5rem", lineHeight: 1.6 }}>
        Avatar personas should describe a role or style — &quot;wise elderly astrologer&quot;,
        &quot;friendly businessman&quot; — not a request to look like a specific named real
        person. Requests that read that way are declined before any image is generated.
      </p>

      <h2 style={{ fontSize: "1.05rem", fontWeight: 600, marginTop: "2rem" }}>AI-generated content is marked</h2>
      <p style={{ color: "var(--text-dim)", marginTop: "0.5rem", lineHeight: 1.6 }}>
        Every video this site renders carries an &quot;AI-generated&quot; tag embedded in the
        file itself, regardless of mode or voice.
      </p>

      <p style={{ marginTop: "2rem" }}>
        <Link href="/privacy" style={{ color: "var(--accent)" }}>Privacy & data</Link>
        {" · "}
        <Link href="/licenses" style={{ color: "var(--accent)" }}>Licenses</Link>
        {" · "}
        <Link href="/" style={{ color: "var(--accent)" }}>Back to your library</Link>
      </p>
    </main>
  );
}
