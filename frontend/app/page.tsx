import Link from "next/link";

export default function Home() {
  return (
    <main className = "flex min-h-screen flex-col items-center justify-center gap-8 p-8">
      <h1 className = "text-3xl font-bold"> Helpdesk Agent </h1>
      <p className = "text-gray-600 text-center max-w-md">
        AI-powered customer support chatbot platform for commercial-grade usage. B2B business -
        Upload your docs, embed the widget, and let it answer your customers&apos; questions.
      </p>
      <Link
      href = "/login"
      className = "rounded-md bg-black px-4 py-2 text-white hover:bg-gray-800">
        LOG IN &lt;3
      </Link>
    </main> 
  );
}