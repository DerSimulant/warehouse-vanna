import { useAuth } from "../auth/AuthContext";

export default function LogoutButton() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <button onClick={logout} className="btn btn-warning btn-sm">
      Logout {user.username}
    </button>
  );
}
