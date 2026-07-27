import { ScanForm } from "@/components/scan-form";

export default function HomePage() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-10 px-6 py-16">
      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">AI Website QA Platform</h1>
        <p className="text-(--color-ink-muted)">
          Enter a URL to audit SEO, accessibility, performance, images, design, content, and
          bugs — then export a client-ready report.
        </p>
      </header>

      <section className="rounded-xl border border-(--color-border-subtle) p-6">
        <ScanForm />
      </section>
    </main>
  );
}
