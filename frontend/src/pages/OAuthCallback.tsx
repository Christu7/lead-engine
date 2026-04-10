import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function OAuthCallback() {
  const navigate = useNavigate();
  const { loginWithToken } = useAuth();

  useEffect(() => {
    // Token is delivered in the URL fragment (#token=...) so it is never
    // sent to the server as part of the request URI.
    const hash = window.location.hash;
    const params = new URLSearchParams(hash.slice(1));
    const token = params.get("token");

    if (token) {
      // Remove the fragment from the address bar before doing anything else so
      // the token cannot be retrieved from the session history.
      history.replaceState(null, "", window.location.pathname + window.location.search);
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
