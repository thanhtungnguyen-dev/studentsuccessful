"use client";
import { LoadingState } from "../ui/LoadingState";
import Link from "next/link";
import { PageHeader } from "../ui/PageHeader";
import {type ReactNode} from "react";
import {useAuth} from "../auth/AuthProvider";
export function PortfolioPage({title,children}:{title:string;children:ReactNode}) {
 const {user,error,refresh}=useAuth();
 return <main className="auth-shell preferences-shell"><Link href="/" className="brand">StudentSuccessful</Link><PageHeader title={title} />
 {user===undefined ? error ? <><p role="alert">{error}</p><button className="secondary" onClick={()=>void refresh().catch(()=>{})}>Retry session</button></> : <LoadingState label="Checking your session…" /> : user===null ? <p>Please <Link href="/login">Login</Link> to manage {title.toLowerCase()}.</p> : <div key={user.id}>{children}</div>}
 </main>;
}
