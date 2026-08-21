.PHONY: deploy-production deploy-production-dry-run rollback-admin-h5

# Thin wrappers only -- all real logic lives in the scripts themselves.
# See docs/production-deployment.md for the full contract.

deploy-production:
	./scripts/deploy-production.sh

deploy-production-dry-run:
	./scripts/deploy-production.sh --dry-run

rollback-admin-h5:
	./scripts/rollback-admin-h5.sh $(SHA)
