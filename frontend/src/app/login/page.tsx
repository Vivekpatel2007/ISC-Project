'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getLoginPath } from '@/lib/login-portal';

export default function LoginPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getLoginPath());
  }, [router]);

  return <p role="status" className="p-8 text-center text-sm text-slate-600">Opening your login portal...</p>;
}
