"use client";

import Link from "next/link";
import { MessageSquare, FileText, BarChart3, Sparkles, ArrowRight } from "lucide-react";

const FEATURES = [
  {
    icon: FileText,
    title: "Upload your docs",
    description: "Drop in PDFs, FAQs, or manuals — HIKA turns them into a searchable knowledge base in seconds.",
  },
  {
    icon: MessageSquare,
    title: "Embed your widget",
    description: "One script tag. Paste it into your site and a branded chat bubble goes live instantly.",
  },
  {
    icon: BarChart3,
    title: "Watch it work",
    description: "Real conversations, real analytics — see exactly what your customers are asking, live.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-obsidian relative overflow-hidden">
      {/* Ambient background elements */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 h-96 w-96 rounded-full bg-accent-indigo opacity-20 blur-[100px] animate-float-slow" />
        <div className="absolute top-1/3 -right-32 h-80 w-80 rounded-full bg-accent-violet opacity-20 blur-[100px] animate-float-slower" />
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
      </div>

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-6 max-w-7xl mx-auto">
<div className="flex flex-col">
  <span className="text-xl font-semibold text-text-primary tracking-tight">HIKA</span>
  <span className="text-[10px] text-text-muted tracking-wide uppercase -mt-0.5">
    Helpdesk Intelligence &amp; Knowledge Automation
  </span>
</div>        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="text-sm font-medium text-text-secondary hover:text-text-primary transition-colors px-4 py-2"
          >
            Log in
          </Link>
          <Link
            href="/signup"
            className="text-sm font-medium text-white bg-gradient-brand rounded-lg px-4 py-2 shadow-glow hover:brightness-110 transition-all"
          >
            Sign up
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <div className="relative z-10 max-w-7xl mx-auto px-8 pt-16 pb-24 grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
        <div>
          <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium bg-gradient-brand-soft text-accent-violet mb-6">
            <Sparkles className="h-3.5 w-3.5" />
            AI-powered customer support
          </span>

          <h1 className="text-5xl sm:text-6xl font-semibold tracking-tight text-text-primary leading-[1.05] mb-6">
            Turn your docs into a{" "}
            <span className="bg-gradient-brand bg-clip-text text-transparent">
              24/7 support agent
            </span>
          </h1>

          <p className="text-lg text-text-secondary max-w-md mb-8 leading-relaxed">
            Upload your documentation, embed one script, and let HIKA answer your
            customers' questions instantly — grounded entirely in your own content.
          </p>

          <div className="flex items-center gap-4">
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 text-sm font-medium text-white bg-gradient-brand rounded-lg px-5 py-3 shadow-glow hover:brightness-110 hover:shadow-lg transition-all"
            >
              Get started free
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/login"
              className="text-sm font-medium text-text-secondary hover:text-text-primary transition-colors px-5 py-3"
            >
              Log in
            </Link>
          </div>
        </div>

        {/* Mock widget preview */}
        <div className="relative">
          <div className="absolute -inset-4 bg-gradient-brand opacity-20 blur-2xl rounded-3xl" />
          <div className="relative glass rounded-2xl p-5 max-w-sm mx-auto animate-float-slow">
            <div className="flex items-center gap-2 mb-4 pb-4 border-b border-white/[0.08]">
              <div className="h-8 w-8 rounded-full bg-gradient-brand flex items-center justify-center">
                <MessageSquare className="h-4 w-4 text-white" />
              </div>
              <span className="text-sm font-medium text-text-primary">HIKA Assistant</span>
              <span className="ml-auto h-2 w-2 rounded-full bg-status-active" />
            </div>

            <div className="flex flex-col gap-3">
              <div className="self-start max-w-[85%] rounded-2xl rounded-bl-sm bg-white/[0.06] px-4 py-2.5 text-sm text-text-primary">
                Hi! How can I help you today?
              </div>
              <div className="self-end max-w-[85%] rounded-2xl rounded-br-sm bg-gradient-brand px-4 py-2.5 text-sm text-white">
                Do you offer refunds?
              </div>
              <div className="self-start max-w-[85%] rounded-2xl rounded-bl-sm bg-white/[0.06] px-4 py-2.5 text-sm text-text-primary flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-text-muted animate-bounce [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 rounded-full bg-text-muted animate-bounce [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 rounded-full bg-text-muted animate-bounce" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Feature cards */}
      <div className="relative z-10 max-w-7xl mx-auto px-8 pb-24">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {FEATURES.map(({ icon: Icon, title, description }) => (
            <div key={title} className="glass glass-hover rounded-xl2 p-6">
              <div className="h-10 w-10 rounded-lg bg-gradient-brand-soft flex items-center justify-center mb-4">
                <Icon className="h-5 w-5 text-accent-violet" />
              </div>
              <h3 className="text-base font-medium text-text-primary mb-2">{title}</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{description}</p>
            </div>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes float-slow {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-16px); }
        }
        @keyframes float-slower {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(20px); }
        }
        .animate-float-slow {
          animation: float-slow 6s ease-in-out infinite;
        }
        .animate-float-slower {
          animation: float-slower 8s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}
