// specs/04-tasks/task-21-launch.md: "ToS + privacy page: what's stored
// (selfies, voice samples, consent records), retention windows, deletion
// rights." Static, no auth required.
import Link from "next/link";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginTop: "2rem" }}>
      <h2 style={{ fontSize: "1.05rem", fontWeight: 600 }}>{title}</h2>
      <div style={{ color: "var(--text-dim)", marginTop: "0.5rem", lineHeight: 1.6 }}>{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "4rem 1.5rem" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>Privacy & data</h1>
      <p style={{ color: "var(--text-dim)", marginTop: "1rem", lineHeight: 1.6 }}>
        This is a private, invite-only site for 1–2 known users. There is no advertising, no
        analytics tracking, and nothing here is sold or shared with anyone.
      </p>

      <Section title="What's stored">
        <ul style={{ paddingLeft: "1.25rem" }}>
          <li>Your account: email and a hashed password (never the plain password itself).</li>
          <li>Scripts, project metadata, and rendered videos you create.</li>
          <li>Selfie photos and generated avatar portraits, if you use Mode A.</li>
          <li>Voice recordings and the tone-color embedding extracted from them, if you enroll your voice.</li>
          <li>
            A consent record (a timestamp) against every selfie and voice sample, confirming you
            affirmed it was your own likeness before it was used.
          </li>
        </ul>
      </Section>

      <Section title="Retention">
        <ul style={{ paddingLeft: "1.25rem" }}>
          <li>
            <strong>Rendered videos</strong> are automatically deleted 14 days after their most
            recent render. The project, script, and any avatar/voice profile used are kept — you
            can re-render for free at any time, with no re-upload needed.
          </li>
          <li>
            <strong>Selfies, portraits, and voice samples</strong> are kept indefinitely so avatars
            can be restyled and voices reused without re-recording — until you delete them yourself.
          </li>
          <li>A nightly encrypted-in-transit backup of the database (not media files) is kept off-server for disaster recovery.</li>
        </ul>
      </Section>

      <Section title="Deletion">
        <p>
          Every selfie, avatar, and voice profile has a delete button that removes the file(s) and
          any derived data (styled portraits, tone-color embeddings) immediately — not just a
          hidden flag. Deleting your account removes everything tied to it.
        </p>
      </Section>

      <Section title="Third parties involved in rendering">
        <p>
          Selfies are sent to Google&apos;s Gemini API only for avatar styling. Script text is sent
          to Gemini for generation/improvement. Scene search terms (not your script or personal
          data) are sent to Pexels/Pixabay for stock images. Narration audio passes through
          Microsoft&apos;s edge-tts service as a base voice before any personal-voice conversion,
          which happens locally on this project&apos;s own server. See{" "}
          <Link href="/licenses" style={{ color: "var(--accent)" }}>Licenses & third-party terms</Link>{" "}
          for the full list.
        </p>
      </Section>

      <p style={{ marginTop: "2rem" }}>
        <Link href="/responsible-use" style={{ color: "var(--accent)" }}>Responsible use</Link>
        {" · "}
        <Link href="/licenses" style={{ color: "var(--accent)" }}>Licenses</Link>
      </p>
    </main>
  );
}
