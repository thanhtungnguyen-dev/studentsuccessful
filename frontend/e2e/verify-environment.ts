import { execFileSync } from "node:child_process";
import path from "node:path";

export default function verifyEnvironment() {
  const project = process.env.E2E_COMPOSE_PROJECT!;
  const ids = execFileSync("docker", ["compose", "-p", project, "ps", "-q", "frontend"], { cwd: path.resolve(__dirname, "../.."), encoding: "utf8" }).trim();
  if (!ids || ids.includes("\n")) throw new Error("Expected exactly one disposable frontend container");
  const [container] = JSON.parse(execFileSync("docker", ["inspect", ids], { encoding: "utf8" }));
  const bindings = container.NetworkSettings.Ports["3000/tcp"];
  if (container.Config.Labels["com.docker.compose.project"] !== project || container.State.Health?.Status !== "healthy"
      || !bindings?.some((binding: { HostIp: string; HostPort: string }) => binding.HostIp === "127.0.0.1" && binding.HostPort === "3000")) {
    throw new Error("E2E requires the named healthy disposable frontend on loopback port 3000");
  }
}
