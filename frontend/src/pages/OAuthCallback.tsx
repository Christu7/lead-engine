import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function OAuthCallback() {
  const navigate = useNavigate();
  const { loginWithToken } = useAuth();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (token) {
      loginWithToken(token);
      navigate("/", { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  }, [loginWithToken, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100">
      <p className="text-gray-500">Signing in…</p>
    </div>
  );
}
