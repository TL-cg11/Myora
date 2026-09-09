import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { getAuthToken, getMe, loginAccount, logoutAccount, registerAccount, setAuthToken } from '../lib/api.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getAuthToken()));

  useEffect(() => {
    let alive = true;
    const expire = () => { setUser(null); setLoading(false); };
    globalThis.addEventListener('myohan-auth-expired', expire);
    if (getAuthToken()) getMe().then((value) => alive && setUser(value)).catch(() => {}).finally(() => alive && setLoading(false));
    return () => { alive = false; globalThis.removeEventListener('myohan-auth-expired', expire); };
  }, []);

  const value = useMemo(() => ({
    user, loading,
    async login(form) {
      const result = await loginAccount(form);
      setAuthToken(result.access_token); setUser(result.user);
      return result.user;
    },
    async register(form) {
      const result = await registerAccount(form);
      setAuthToken(result.access_token); setUser(result.user);
      return result.user;
    },
    async logout() {
      try { await logoutAccount(); } finally { setAuthToken(null); setUser(null); }
    },
  }), [user, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider가 필요합니다.');
  return value;
}
