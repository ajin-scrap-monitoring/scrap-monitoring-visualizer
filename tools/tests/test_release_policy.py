import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.check_release import project_version, validate_release


class ReleasePolicyTest(unittest.TestCase):
    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "tag.gpgsign", "false")
        (self.root / "src/scrap_monitoring_visualizer").mkdir(parents=True)
        (self.root / "edge-bridge").mkdir()
        (self.root / "pyproject.toml").write_text(
            '[project]\nversion = "1.2.3"\n', encoding="utf-8"
        )
        (self.root / "src/scrap_monitoring_visualizer/__init__.py").write_text(
            '__version__ = "1.2.3"\n', encoding="utf-8"
        )
        (self.root / "edge-bridge/Cargo.toml").write_text(
            '[package]\nname = "fixture-edge-bridge"\nversion = "1.2.3"\n',
            encoding="utf-8",
        )
        self.git("add", ".")
        self.git("commit", "--allow-empty", "-m", "Initial fixture")
        self.base = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.git("tag", "v1.2.3", self.base)

    def test_version_tag_on_main(self):
        self.assertEqual(validate_release(self.root, "v1.2.3", self.base), "1.2.3")

    def test_annotated_tag_on_main(self):
        self.git("tag", "-d", "v1.2.3")
        self.git("tag", "-a", "v1.2.3", "-m", "Annotated fixture", self.base)
        self.assertEqual(validate_release(self.root, "v1.2.3", "v1.2.3"), "1.2.3")

    def test_invalid_tag_names(self):
        for tag in ("latest", "1.2.3", "v1.2", "v1.2.3-rc1", "v1.2.3\n"):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "tag must"):
                validate_release(self.root, tag, self.base)

    def test_tag_outside_main_is_rejected(self):
        self.git("commit", "--allow-empty", "-m", "Unmerged fixture")
        commit = self.git("rev-parse", "HEAD")
        self.git("tag", "v2.0.0", commit)
        with self.assertRaisesRegex(ValueError, "part of origin/main"):
            validate_release(self.root, "v2.0.0", commit)

    def test_tag_revision_mismatch_is_rejected(self):
        self.git("commit", "--allow-empty", "-m", "Another fixture")
        with self.assertRaisesRegex(ValueError, "does not identify"):
            validate_release(self.root, "v1.2.3", "HEAD")

    def test_tag_must_match_package_version(self):
        self.git("tag", "v1.2.4", self.base)
        with self.assertRaisesRegex(ValueError, "package version"):
            validate_release(self.root, "v1.2.4", self.base)

    def test_version_declarations_must_match(self):
        (self.root / "src/scrap_monitoring_visualizer/__init__.py").write_text(
            '__version__ = "2.0.0"\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "do not match"):
            project_version(self.root)

    def test_edge_bridge_version_must_match(self):
        (self.root / "edge-bridge/Cargo.toml").write_text(
            '[package]\nname = "fixture-edge-bridge"\nversion = "2.0.0"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "do not match"):
            project_version(self.root)


class ReleaseWorkflowPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.candidate = (cls.root / ".github/workflows/candidate.yml").read_text(
            encoding="utf-8"
        )
        cls.ci = (cls.root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        cls.release = (cls.root / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        cls.server_compose = (cls.root / "deploy/server/compose.yml").read_text(
            encoding="utf-8"
        )
        cls.server_service = (
            cls.root / "deploy/server/scrap-monitoring-visualizer.service"
        ).read_text(encoding="utf-8")
        cls.server_setup = (cls.root / "deploy/server/setup.sh").read_text(
            encoding="utf-8"
        )

    def assert_strict_attestation_verification(self, workflow: str) -> None:
        self.assertNotIn("--format '{{json .SBOM}}'", workflow)
        self.assertNotIn("--format '{{json .Provenance}}'", workflow)
        self.assertNotIn("contains_key", workflow)
        required = (
            "application/vnd.oci.image.index.v1+json",
            '== "attestation-manifest"',
            'entry.get("annotations", {}).get("vnd.docker.reference.digest")',
            "== runnable_digest",
            "application/vnd.docker.attestation.manifest.v1+json",
            'manifest.get("subject", {}).get("digest") != sys.argv[2]',
            'layer.get("mediaType") != "application/vnd.in-toto+json"',
            "https://spdx.dev/Document",
            "https://slsa.dev/provenance/v1",
            '"$image_name@$attestation_digest"',
        )
        for contract in required:
            self.assertEqual(workflow.count(contract), 1)
        self.assertEqual(workflow.count("          verify_image \\\n"), 2)

    def test_ci_keeps_required_job_and_builds_edge_bridge(self):
        self.assertIn("    name: CI\n", self.ci)
        self.assertIn("    timeout-minutes: 45\n", self.ci)
        self.assertIn("--target test", self.ci)
        self.assertIn("file: Dockerfile.edge-bridge", self.ci)
        self.assertIn("platforms: linux/arm64", self.ci)
        self.assertIn("target: runtime", self.ci)

    def test_workflows_pin_one_emulation_and_builder_stack(self):
        required = (
            "docker/setup-qemu-action@99012661954931238ded8c8b007157a8430204e1",
            "docker.io/tonistiigi/binfmt:qemu-v10.2.3-68@sha256:"
            "400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0",
            "docker/setup-buildx-action@594f3bf4285d9ea8dc53c9a0c9c4092420091003",
            "version: v0.37.1",
            "image=docker.io/moby/buildkit:v0.33.0@sha256:"
            "6c2fa84a6b61ccd72899dde4239f8d5717f05f9a8ca6f3cad185fb1a95a94de3",
        )
        for name, workflow in (
            ("CI", self.ci),
            ("Candidate", self.candidate),
            ("Release", self.release),
        ):
            with self.subTest(workflow=name):
                for dependency in required:
                    self.assertEqual(workflow.count(dependency), 1)

    def test_workflows_prepare_headless_source_rendering(self):
        required = (
            "sudo apt-get install --yes --no-install-recommends libegl1 libgl1",
            'LIBGL_ALWAYS_SOFTWARE: "1"',
            'PYVISTA_OFF_SCREEN: "true"',
            "VTK_DEFAULT_OPENGL_WINDOW: vtkEGLRenderWindow",
        )
        for name, workflow in (
            ("CI", self.ci),
            ("Candidate", self.candidate),
            ("Release", self.release),
        ):
            with self.subTest(workflow=name):
                for setting in required:
                    self.assertEqual(workflow.count(setting), 1)

    def test_release_publishes_two_attested_platform_images(self):
        self.assertIn("platforms: linux/amd64", self.release)
        self.assertIn("platforms: linux/arm64", self.release)
        self.assertIn("file: Dockerfile.edge-bridge", self.release)
        self.assertEqual(self.release.count("provenance: mode=max"), 2)
        self.assertEqual(self.release.count("sbom: true"), 2)
        self.assert_strict_attestation_verification(self.release)
        self.assertIn('verify_visibility "$VISUALIZER_IMAGE_NAME"', self.release)
        self.assertIn('verify_visibility "$EDGE_BRIDGE_IMAGE_NAME"', self.release)
        self.assertEqual(self.release.count('verify_visibility "$'), 2)
        self.assertIn(
            'edge_bridge_image_name="ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/'
            'scrap-monitoring-visualizer-edge-bridge"',
            self.release,
        )
        self.assertIn(
            "edge_bridge_revision_ref=$edge_bridge_image_name:sha-$GITHUB_SHA",
            self.release,
        )
        self.assertIn(
            "edge_bridge_version_ref=$edge_bridge_image_name:$version", self.release
        )

    def test_release_keeps_per_image_idempotency_and_draft_publication(self):
        self.assertIn("${output_prefix}_publish=true", self.release)
        self.assertIn("manifest unknown|name unknown|not found", self.release)
        self.assertIn("${output_prefix}_missing_ref=$revision_ref", self.release)
        self.assertIn("${output_prefix}_missing_ref=$version_ref", self.release)
        self.assertIn("docker buildx imagetools create \\", self.release)
        self.assertIn("image tag recovery did not preserve the digest", self.release)
        for prefix in ("visualizer", "edge_bridge"):
            self.assertIn(f"steps.existing.outputs.{prefix}_publish", self.release)
            self.assertIn(f"steps.existing.outputs.{prefix}_missing_ref", self.release)
        create_at = self.release.index("gh release create")
        publish_at = self.release.index(
            'gh release edit "$GITHUB_REF_NAME" --draft=false --latest'
        )
        self.assertLess(create_at, publish_at)
        self.assertIn("--draft", self.release[create_at:publish_at])

    def test_release_assets_identify_both_images(self):
        self.assertIn("release/oci-image.txt", self.release)
        self.assertIn("release/edge-bridge-oci-image.txt", self.release)
        self.assertIn("edge-bridge-oci-image.txt \\", self.release)
        self.assertIn("images: {", self.release)
        self.assertIn("visualizer: {", self.release)
        self.assertIn("edge_bridge: {", self.release)

    def test_release_contains_checked_deployment_bundle(self):
        self.assertIn("git archive \\", self.release)
        self.assertIn(".env.example \\", self.release)
        self.assertIn("deploy \\", self.release)
        self.assertIn("gzip -n > release/deployment.tar.gz", self.release)
        self.assertIn("deployment.tar.gz \\", self.release)

    def test_server_lifecycle_waits_for_tailnet_before_foreground_compose(self):
        self.assertIn("tailscale wait --timeout=120s", self.server_service)
        self.assertIn("tailscale ip --assert=", self.server_service)
        self.assertIn("run-visualizer start", self.server_service)
        self.assertIn("Restart=always", self.server_service)
        self.assertIn('restart: "no"', self.server_compose)

    def test_server_setup_rolls_back_after_session_disconnect(self):
        self.assertIn("trap 'rollback 129' HUP", self.server_setup)
        self.assertEqual(self.server_setup.count("trap - ERR HUP INT TERM"), 2)

    def test_candidate_is_manual_and_requires_current_main(self):
        trigger = self.candidate.split("permissions:", maxsplit=1)[0]
        self.assertIn("  workflow_dispatch:\n", trigger)
        self.assertNotIn("  pull_request:", trigger)
        self.assertNotIn("  push:", trigger)
        self.assertIn("  packages: write\n", self.candidate)
        self.assertIn('"$GITHUB_REF" != "refs/heads/main"', self.candidate)
        self.assertIn('"$GITHUB_SHA" != "$main_commit"', self.candidate)
        self.assertIn("refs/remotes/origin/main^{commit}", self.candidate)

    def test_candidate_uses_only_sha_scoped_candidate_tags(self):
        self.assertIn('candidate_tag="candidate-sha-$GITHUB_SHA"', self.candidate)
        tag_lines = [
            line.strip()
            for line in self.candidate.splitlines()
            if line.strip().startswith("tags:")
        ]
        self.assertEqual(
            tag_lines,
            [
                "tags: ${{ steps.candidate.outputs.visualizer_candidate_ref }}",
                "tags: ${{ steps.candidate.outputs.edge_bridge_candidate_ref }}",
            ],
        )
        self.assertNotIn("visualizer_version_ref", self.candidate)
        self.assertNotIn("visualizer_revision_ref", self.candidate)
        self.assertNotIn("edge_bridge_version_ref", self.candidate)
        self.assertNotIn("edge_bridge_revision_ref", self.candidate)
        self.assertNotIn("git tag", self.candidate)

    def test_candidate_publishes_and_verifies_two_attested_images(self):
        self.assertIn("platforms: linux/amd64", self.candidate)
        self.assertIn("platforms: linux/arm64", self.candidate)
        self.assertEqual(self.candidate.count("provenance: mode=max"), 2)
        self.assertEqual(self.candidate.count("sbom: true"), 2)
        self.assert_strict_attestation_verification(self.candidate)
        self.assertIn(
            "org.opencontainers.image.revision=${{ github.sha }}", self.candidate
        )
        self.assertIn("$candidate_digest", self.candidate)
        self.assertIn("tools/generate_edge_bridge_notices.py --check", self.candidate)

    def test_candidate_verifies_public_packages_and_reports_digest_refs(self):
        self.assertNotIn("--method PATCH", self.candidate)
        self.assertNotIn("--field visibility=public", self.candidate)
        self.assertEqual(self.candidate.count('verify_public "$'), 2)
        self.assertIn('>> "$GITHUB_STEP_SUMMARY"', self.candidate)
        self.assertIn("$VISUALIZER_IMAGE_NAME@$VISUALIZER_DIGEST", self.candidate)
        self.assertIn("$EDGE_BRIDGE_IMAGE_NAME@$EDGE_BRIDGE_DIGEST", self.candidate)


if __name__ == "__main__":
    unittest.main()
