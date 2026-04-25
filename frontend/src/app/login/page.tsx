"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiClient, ApiError } from "@/lib/api";
import { saveToken } from "@/lib/auth";
import { m } from "@/paraglide/messages.js";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!username || !password) return;
    setIsSubmitting(true);
    try {
      const res = await apiClient.login(username, password);
      saveToken(res.access_token);
      router.push("/");
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : m.errors_login_failed();
      toast.error(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{m.auth_login_title()}</CardTitle>
          <CardDescription>{m.auth_login_description()}</CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit}>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="username">{m.auth_username_label()}</Label>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">{m.auth_password_label()}</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3 items-stretch">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? m.auth_logging_in() : m.auth_login_button()}
            </Button>
            <p className="text-sm text-muted-foreground text-center">
              {m.auth_register_link_prefix()}{" "}
              <Link href="/register" className="underline">
                {m.auth_register_link()}
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </main>
  );
}
