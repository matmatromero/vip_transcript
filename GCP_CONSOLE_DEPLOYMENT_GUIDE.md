# GCP Console Deployment Guide (No Terminal Required)

This guide walks you through deploying the semantic chunking and RAG pipeline entirely through the visual **Google Cloud Platform (GCP) Web Console**.

## 1. Create Storage Buckets (Google Cloud Storage)
1. In the GCP Console search bar, type **Cloud Storage** and go to **Buckets**.
2. Click **+ CREATE**.
3. Name your first bucket (e.g., `company-transcripts-raw`). This is where you will drop the `.txt` files.
4. Click **CREATE**.
5. Repeat the process to create a second bucket (e.g., `company-transcripts-processed`) for JSON backups.

## 2. Set Up the RAG Database (Cloud SQL)
1. Search for **Cloud SQL** and select it.
2. Click **CREATE INSTANCE** and choose **PostgreSQL**.
3. Name your instance (e.g., `rag-database`) and set a password for the `postgres` user.
4. Expand **Configuration Options** > **Machine type**. Change it to `Shared Core (db-f1-micro)` to keep costs incredibly low for testing.
5. Click **CREATE INSTANCE** (This takes ~5-10 minutes to spin up).
6. Once active, click into the instance and go to the **Databases** tab on the left. Click **CREATE DATABASE** and name it `rag_db`.
7. Go to **Cloud SQL Studio** (on the left menu) to open a web-based querying interface. Log in with the password you set, paste the contents of `schema.sql`, and hit **RUN**. Your `pgvector` table is now ready!

## 3. Enable Vertex AI
1. Search for **Vertex AI API** and click on it.
2. Click **ENABLE API**. (This authorizes your project to use Google's serverless embedders without needing to provision servers or manage API keys).

## 4. Deploy the Pipeline (Cloud Run)
*Note: To deploy via the UI without the terminal, your code needs to be on GitHub. If you aren't using GitHub, you can open the browser-based Cloud Shell, click "Upload Folder", and run a single build command.* 

Assuming your code is in a GitHub repository:
1. Search for **Cloud Run** and click on it.
2. Click **DEPLOY CONTAINER**, then select **Service**.
3. Select **Continuously deploy new revision from a source repository**.
4. Click **SET UP WITH CLOUD BUILD**. Authenticate your GitHub account and select this repository. 
5. Under Build Configuration, select **Dockerfile** and ensure the path is just `/Dockerfile`. Click **SAVE**.
6. **Container Configurations:** Under "Variables & Secrets", you will define your environment variables so the script knows where the database is. Add:
   *   `DB_HOST` = [Your Cloud SQL IP Address]
   *   `DB_PASS` = [Your Cloud SQL Password]
7. Click **CREATE**. Cloud Run will now pull your repository and build the Docker container automatically!

## 5. Automate with Eventarc (The Trigger)
Once your Cloud Run service successfully deploys and goes green:
1. Click into your new Cloud Run service.
2. On the top menu, click **+ ADD EVENTARC TRIGGER**.
3. Set the **Event Provider** to `Cloud Storage`.
4. Set the **Event Type** to `google.cloud.storage.object.v1.finalized` (This means "when a new file is uploaded/finalized").
5. Select your `company-transcripts-raw` bucket from the dropdown.
6. Click **SAVE TRIGGER**.

### 🎉 You are Done!
**How to test it:** Navigate to your `company-transcripts-raw` bucket in the UI. Click **Upload Files** and select `tesla_Q1.txt`. 

As soon as the file finishes uploading, Eventarc triggers Cloud Run. Cloud Run processes the transcript into semantic chunks, queries Vertex AI for the mathematical embeddings, and pushes the data into your Cloud SQL database. Use the "Logs" tab in Cloud Run to watch it happen live!
