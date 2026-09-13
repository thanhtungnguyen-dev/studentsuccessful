"use client";
import Link from "next/link";
import {type ReactNode} from "react";
import {useAuth} from "../auth/AuthProvider";
export function PortfolioPage({title,children}:{title:string;children:ReactNode}) {
 const {user,error,refresh}=useAuth();
 return <main className="auth-shell preferences-shell"><Link href="/" className="brand">StudentSuccessful</Link><h1 className="profile-title">{title}</h1>
 {user===undefined ? error ? <><p role="alert">{error}</p><button className="secondary" onClick={()=>void refresh().catch(()=>{})}>Retry session</button></> : <p role="status">Checking your session…</p> : user===null ? <p>Please <Link href="/login">Login</Link> to manage {title.toLowerCase()}.</p> : <div key={user.id}>{children}</div>}
 </main>;
}
