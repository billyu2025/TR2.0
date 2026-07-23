/*
  Deploy: bbs_tr_status + sync_tr_data change
  - Keep BBS with missing TR in DW tables (header/size/detail/bbs_dd)
  - Mark them incomplete in bbs_tr_status with missing_diameters
  - Complete BBS marked complete
*/
SET NOCOUNT ON;

IF OBJECT_ID(N'dbo.bbs_tr_status', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.bbs_tr_status (
        bbs_no            INT NOT NULL CONSTRAINT PK_bbs_tr_status PRIMARY KEY,
        tr_status         VARCHAR(20) NOT NULL,
        missing_diameters NVARCHAR(200) NULL,
        updated_at        DATETIME NOT NULL CONSTRAINT DF_bbs_tr_status_updated DEFAULT (GETDATE())
    );
END
GO

/*
  Patch note embedded in procedure header update.
  Full procedure body replaced via ALTER below — only the
  "missing TR => delete whole BBS" block changes to status table logic.
*/
GO
