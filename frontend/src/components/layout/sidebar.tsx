'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  UploadCloud,
  FileText,
  UserCircle,
  LogOut,
  ShieldCheck,
  Activity,
  Stethoscope,
} from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { cn } from '@/lib/utils';

interface SidebarProps {
  onNavClick?: () => void;
}

export function Sidebar({ onNavClick }: SidebarProps) {
  const pathname = usePathname();
  const { user, role, logout } = useAuth();

  const navItems = [
    {
      label: 'Dashboard',
      href: '/',
      icon: LayoutDashboard,
      description: 'System overview & metrics',
    },
    {
      label: 'Upload Radiograph',
      href: '/upload',
      icon: UploadCloud,
      description: 'Secure AES-256 upload',
    },
    {
      label: 'Scan Repository',
      href: '/scans',
      icon: FileText,
      description: 'History & inference',
    },
    {
      label: 'Staff Profile',
      href: '/profile',
      icon: UserCircle,
      description: 'Role & credentials',
    },
  ];

  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col h-full select-none">
      {/* Brand Header */}
      <div className="p-5 border-b border-slate-100 flex items-center space-x-3">
        <div className="h-10 w-10 rounded-lg bg-sky-600 flex items-center justify-center text-white shadow-sm shadow-sky-200">
          <Activity className="h-6 w-6 stroke-[2.2]" />
        </div>
        <div>
          <div className="flex items-center space-x-1.5">
            <span className="font-bold text-lg text-slate-900 tracking-tight">PulmoScan</span>
            <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">
              AI
            </span>
          </div>
          <p className="text-xs text-slate-500 font-medium">Chest X-Ray Screening</p>
        </div>
      </div>

      {/* Nav List */}
      <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
        <div className="px-3 py-2 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
          Clinical Navigation
        </div>
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavClick}
              className={cn(
                'flex items-center space-x-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-sky-50 text-sky-800 font-semibold shadow-xs'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              )}
            >
              <Icon
                className={cn(
                  'h-4.5 w-4.5 shrink-0',
                  isActive ? 'text-sky-600' : 'text-slate-400'
                )}
              />
              <span className="flex-1 truncate">{item.label}</span>
            </Link>
          );
        })}

        {/* Security badge note */}
        <div className="pt-4 px-3">
          <div className="rounded-lg bg-slate-50 border border-slate-200/80 p-3 text-xs text-slate-600">
            <div className="flex items-center space-x-2 text-slate-800 font-medium mb-1">
              <ShieldCheck className="h-4 w-4 text-teal-600 shrink-0" />
              <span>AES-256-GCM At Rest</span>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              Encrypted storage & zero plaintext on disk.
            </p>
          </div>
        </div>
      </nav>

      {/* Authenticated Practitioner Footer */}
      <div className="p-4 border-t border-slate-100 bg-slate-50/70">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center space-x-2.5 min-w-0">
            <div className="h-8 w-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-700 font-semibold text-xs shrink-0">
              <Stethoscope className="h-4 w-4 text-slate-600" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-slate-900 truncate">
                {user?.full_name || user?.username || 'Staff'}
              </p>
              <span
                className={cn(
                  'inline-block text-[10px] font-semibold uppercase px-1.5 py-0.2 rounded mt-0.5',
                  role === 'doctor'
                    ? 'bg-blue-100 text-blue-800'
                    : role === 'radiologist'
                    ? 'bg-teal-100 text-teal-800'
                    : 'bg-slate-200 text-slate-700'
                )}
              >
                {role || 'Authorized'}
              </span>
            </div>
          </div>
        </div>

        <button
          onClick={logout}
          className="w-full flex items-center justify-center space-x-2 px-3 py-1.5 text-xs font-medium text-rose-700 bg-white hover:bg-rose-50 border border-rose-200 rounded-md transition-colors"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  );
}
