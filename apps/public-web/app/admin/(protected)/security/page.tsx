import { RoleCreateForm, UserCreateForm, UserStateForm } from "@/components/admin/forms";
import { getAdminSite } from "@/lib/api";

interface Role { id: string; name: string; permissions: string[] }
interface User { id: string; username: string; display_name: string; is_active: boolean; mfa_required: boolean; roles: string[] }
interface Permission { code: string; description?: string }

export default async function SecurityPage() {
  const [users, roles, permissions] = await Promise.all([
    getAdminSite<User[]>("/api/v1/admin/security/users"),
    getAdminSite<Role[]>("/api/v1/admin/security/roles"),
    getAdminSite<Permission[]>("/api/v1/admin/security/permissions"),
  ]);
  return <><header className="admin-heading"><div><p className="kicker">Identity and access</p><h1>Users & roles</h1></div></header><section className="admin-panel"><h2>Create user</h2><UserCreateForm roles={roles} /></section><section className="admin-panel"><h2>Create custom role</h2><RoleCreateForm permissions={permissions} /></section><section className="admin-panel"><h2>Users</h2><div className="table-wrap"><table><thead><tr><th>User</th><th>Roles</th><th>MFA</th><th>Status</th><th>Action</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td>{user.display_name}<br /><small>{user.username}</small></td><td>{user.roles.join(", ")}</td><td>{user.mfa_required ? "Required" : "Optional"}</td><td>{user.is_active ? "Active" : "Disabled"}</td><td><UserStateForm id={user.id} active={user.is_active} /></td></tr>)}</tbody></table></div></section><section className="admin-panel"><h2>Role permissions</h2>{roles.map((role) => <article key={role.id}><strong>{role.name}</strong><p>{role.permissions.join(", ")}</p></article>)}</section></>;
}
