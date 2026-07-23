/*
Created by:		Matthew Au Yeung
Create Date:	2025-11-18
Description:	synchronize TR data from schnell to datawarehouse

Updated by:		Matthew Au Yeung
Update Date:	2026-06-10
Description:	BBS with missing TR still sync to DW; UI marks them incomplete via PG bbs_tr_status.
*/
CREATE PROCEDURE [dbo].[sync_tr_data]
	/*
	@pReportType	nvarchar(20) = 'detail',
	@pFromProdDate	date, 
	@pToProdDate	date,
	@pFromDelDate	date, -- mandatory
	@pToDelDate		date,
	@pJobSite		int = null */
AS
BEGIN
	SET NOCOUNT ON;

	declare @sql nvarchar(max) = ''
	declare @currDate date = dateadd(month, -36, getdate())
	set @currDate = dateadd(day, -DAY(@currDate) + 1, @currDate)

	/*
	CREATE TABLE #t_cert_of_compliance (
		shipping_no        INT NOT NULL,
		del_date           DATE NOT NULL,
		jobsite_no         INT NOT NULL,
		jobsite_name       NVARCHAR(255) NULL,
		del_address        NVARCHAR(255) NULL,
		asd_contract_no1   NVARCHAR(100) NULL,
		asd_contract_no2   NVARCHAR(100) NULL,
		work_order_no      NVARCHAR(20) NULL,
		client_name        NVARCHAR(255) NULL,
		main_contractor   NVARCHAR(100) NULL,
		bbs_no_list        NVARCHAR(100) NULL
	)
	*/

	CREATE TABLE #t_tr_bbs_header (
		bbs_no          INT NOT NULL, -- Primary Key from source
		order_desc      NVARCHAR(200) NULL,
		jobsite_no      INT NOT NULL,
		jobsite_name    NVARCHAR(300) NULL,
		jobsite_type    NVARCHAR(10) NOT NULL,
		main_contractor NVARCHAR(200) NULL,
		delivery_date   DATE NULL,
		bbs_ref_no      NVARCHAR(40) NULL,
		bbs_po_no       NVARCHAR(40) NULL
	)

	CREATE TABLE #t_tr_line_size (
		jobsite_no    INT NOT NULL,
		bbs_no        INT NOT NULL,
		diameter      NVARCHAR(10) NOT NULL,
		wt_ton        DECIMAL(18,5) NOT NULL
	)

	CREATE TABLE #t_tr_line_detail (
		jobsite_no    INT NOT NULL,
		bbs_no        INT NOT NULL,
		diameter      NVARCHAR(10) NOT NULL,
		product       NVARCHAR(100) NULL,
		grade         NVARCHAR(10) NULL,
		pattern       NVARCHAR(10) NULL,
		mill_cert     NVARCHAR(200) NULL,
		test_cert1    NVARCHAR(200) NULL,
		test_cert2    NVARCHAR(200) NULL,
		supplier      NVARCHAR(100) NULL,
		stockist_cert NVARCHAR(20) NULL,
		po_no         NVARCHAR(50) NULL,
		rm_dn_no      NVARCHAR(50) NULL
	)

	CREATE TABLE #t_bbs_dd (
		bbs_no           INT NOT NULL,
		order_desc       NVARCHAR(200) NULL,
		jobsite_no       INT NOT NULL,
		jobsite_type     NVARCHAR(10) NOT NULL,
		dd_no            NVARCHAR(10) NULL,
		dd_delivery_date DATE NULL
	)

	/*
	truncate table cert_of_compliance
	truncate table tr_bbs_header
	truncate table tr_line_size
	truncate table tr_line_detail
	truncate table bbs_dd
	*/

	set @sql = '
		select bbs_no, order_desc, jobsite_no, jobsite_type, dd_no, dd_delivery_date
		from openquery (TVSC, ''
			SELECT ddd.id_pedido_produccion AS bbs_no,
				pp.descripcion AS order_desc, pp.id_obra AS jobsite_no,
				CASE WHEN js.id_tipo_forjado IN (2, 3, 7) THEN ''''PRIVATE'''' ELSE ''''IAT'''' END AS jobsite_type,
				ddh.numero_albaran AS dd_no, ddh.fecha_albaran AS dd_delivery_date
			FROM albaranes_salida ddh
			JOIN albaranes_salida_lin ddd
				ON ddh.id_albaran_salida = ddd.id_albaran_salida
			JOIN pedidos_produccion pp
				ON ddd.id_pedido_produccion = pp.id_pedido_produccion
			JOIN obras js
				ON js.id_obra = pp.id_obra
			WHERE
				ddh.fecha_albaran >= ''''{delivery_date}''''
			GROUP BY ddd.id_pedido_produccion, pp.descripcion, pp.id_obra, ddh.numero_albaran, ddh.fecha_albaran, js.id_tipo_forjado
			ORDER BY ddd.id_pedido_produccion
		'')
	'

	set @sql = replace( @sql, '{delivery_date}', convert(nvarchar(10), @currDate, 120) )

	insert into #t_bbs_dd (bbs_no, order_desc, jobsite_no, jobsite_type,
		dd_no, dd_delivery_date)
	exec (@sql)
	

	set @sql = '
		select id_pedido_produccion,
			descripcion,
			id_obra,
			nombre,
			jobsite_type,
			arquitecto,
			fecha_entrega_prevista,
			referencia_1,
			referencia_2
		from openquery(TVSC, ''
			SELECT pp.id_pedido_produccion, 
				pp.descripcion,
				pp.id_obra,
				js.nombre,
				CASE WHEN js.id_tipo_forjado IN (2, 3, 7) THEN ''''PRIVATE'''' ELSE ''''IAT'''' END AS jobsite_type,
				js.arquitecto,
				pp.fecha_entrega_prevista,
				pp.referencia_1,
				pp.referencia_2
			FROM pedidos_produccion pp
			JOIN obras js
				ON pp.id_obra = js.id_obra
			WHERE
				pp.fecha_entrega_prevista >= ''''{delivery_date}''''
				AND js.id_tipo_forjado NOT IN (10, 12)
				-- AND pp.estado IN (11)
				AND pp.estado = 11 -- added by matthew, 20260610
				AND pp.estado <> 15
				AND EXISTS (SELECT 1 FROM pedidos_produccion_lin ppl
					WHERE ppl.id_pedido_produccion = pp.id_pedido_produccion
						AND ppl.cal_tipo_acero_fa <> ''''460''''
						AND ppl.cal_mm_fa <> 0
						AND ppl.id_albaran_salida IS NOT null
				)
		'')
	'

	set @sql = replace( @sql, '{delivery_date}', convert(nvarchar(10), @currDate, 120) )

	insert into #t_tr_bbs_header (bbs_no, order_desc, jobsite_no, jobsite_name, jobsite_type,
		main_contractor, delivery_date, bbs_ref_no, bbs_po_no)
	exec (@sql)

	--print (@sql)


	set @sql = '
		select id_obra, id_pedido_produccion, diameter, wt_ton
		from openquery(TVSC, ''
			SELECT pp.id_obra, pp.id_pedido_produccion, ppl.cal_nombre_fa AS diameter,
				round(sum(ppl.peso_paquete_fb)/1000, 5) AS wt_ton
			FROM pedidos_produccion pp
			JOIN pedidos_produccion_lin ppl
				ON pp.id_pedido_produccion = ppl.id_pedido_produccion
			JOIN obras js
				ON js.id_obra = pp.id_obra
			WHERE
				ppl.cal_tipo_acero_fa <> ''''460''''
				AND ppl.cal_mm_fa <> 0
				AND pp.fecha_entrega_prevista >= ''''{delivery_date}''''
				AND js.id_tipo_forjado not in ( 10, 12) -- EXCLUDE intercom jobsite
				-- AND pp.estado in (11)
				AND pp.estado = 11 -- added by matthew, 20260610
				AND pp.estado <> 15
				AND EXISTS (SELECT 1 FROM pedidos_produccion_lin ppl
					WHERE ppl.id_pedido_produccion = pp.id_pedido_produccion
						AND ppl.cal_tipo_acero_fa <> ''''460''''
						AND ppl.cal_mm_fa <> 0
						AND ppl.id_albaran_salida IS NOT null
				)
			GROUP BY pp.id_obra, pp.id_pedido_produccion,
				ppl.cal_nombre_fa, js.id_tipo_forjado
		'')
	'

	set @sql = replace( @sql, '{delivery_date}', convert(nvarchar(10), @currDate, 120) )

	insert into #t_tr_line_size (jobsite_no, bbs_no, diameter, wt_ton)
	exec (@sql)

	--print (@sql)

	set @sql = '
		select jobsite_no, bbs_no, diameter,
			product, grade, pattern, mill_cert, test_cert1, test_cert2,
			supplier, stockist_cert, po_no, rm_dn_no
		from openquery(TVSC, ''
			SELECT pp.id_obra AS jobsite_no, pp.id_pedido_produccion AS bbs_no, ppl.cal_nombre_fa AS diameter,
				ael.DESCRIPCION AS product, 
				ppl.cal_tipo_acero_fa AS grade,
				rm.info_1 AS pattern, 
				ael.COLADA_FABRICANTE_2 AS mill_cert,
				-- CASE WHEN js.id_tipo_forjado = 2 THEN ael.CERTIFICADO_NUMERO_2 ELSE ael.CERTIFICADO_NUMERO END AS test_cert,
				ael.CERTIFICADO_NUMERO_2 as test_cert1, -- PRIVATE
				ael.CERTIFICADO_NUMERO as test_cert2, -- IAT
				--ael.CALIDAD_NUMERO_2 AS ha_test_cert,
				--ael.CERTIFICADO_NUMERO_2 AS private_test_cert,
				--ael.CERTIFICADO_NUMERO AS iat_test_cert,
				supplier.nombre AS supplier,
				ae.REFERENCIA_1 AS stockist_cert,
				ae.REFERENCIA_2 AS po_no,
				ae.numero_albaran as rm_dn_no
			FROM pedidos_produccion pp
			JOIN pedidos_produccion_lin ppl
				ON pp.id_pedido_produccion = ppl.id_pedido_produccion
			JOIN pedidos_produccion_traza tr
				ON tr.id_pedido_produccion_lin = ppl.id_pedido_produccion_lin
			JOIN productos_almacen rm
				ON rm.id_producto_almacen = tr.id_producto_almacen
			JOIN albaranes_entrada_lin ael
				ON rm.id_albaran_entrada_lin = ael.id_albaran_entrada_lin
			JOIN albaranes_entrada ae
				ON ae.id_albaran_entrada = ael.id_albaran_entrada
			JOIN productos itm
				ON itm.id_producto = rm.id_producto
			JOIN proveedores supplier
				ON supplier.id_proveedor = ae.id_proveedor
			JOIN obras js
				ON js.id_obra = pp.id_obra
			WHERE 1=1
				AND pp.fecha_entrega_prevista >= ''''{delivery_date}''''
				AND ppl.CAL_TIPO_ACERO_FA <> ''''460''''
				AND ppl.cal_mm_fa <> 0
				AND js.id_tipo_forjado not in ( 10, 12) -- EXCLUDE intercom jobsite
				-- and pp.estado in (11)
				AND pp.estado = 11 -- added by matthew, 20260610
				AND pp.estado <> 15
				AND EXISTS (SELECT 1 FROM pedidos_produccion_lin ppl
					WHERE ppl.id_pedido_produccion = pp.id_pedido_produccion
						AND ppl.cal_tipo_acero_fa <> ''''460''''
						AND ppl.cal_mm_fa <> 0
						AND ppl.id_albaran_salida IS NOT null
				)
			GROUP BY pp.id_obra, pp.id_pedido_produccion, ppl.cal_nombre_fa,
				ael.DESCRIPCION, 
				ppl.cal_tipo_acero_fa,
				rm.info_1, 
				ael.COLADA_FABRICANTE_2,
				ael.CALIDAD_NUMERO_2,
				ael.CERTIFICADO_NUMERO_2,
				ael.CERTIFICADO_NUMERO,
				supplier.nombre,
				ae.REFERENCIA_1,
				ae.REFERENCIA_2,
				js.id_tipo_forjado,
				ae.numero_albaran
		'')
	'
	
	set @sql = replace( @sql, '{delivery_date}', convert(nvarchar(10), @currDate, 120) )

	insert into #t_tr_line_detail ( jobsite_no, bbs_no, diameter,
		product, grade, pattern, mill_cert, test_cert1, test_cert2,
		supplier, stockist_cert, po_no, rm_dn_no )
	exec (@sql)
	
	--print (@sql)

	-- sync cert of compliance data, added by Matthew, 20260603
	set @sql = '
		select shipping_no, del_date, jobsite_no, jobsite_name, del_address, 
			asd_contract_no1, asd_contract_no2, work_order_no, client_name, main_contractor, bbs_no_list
		from openquery(TVSC, ''
			SELECT shipping_no, del_date, jobsite_no, jobsite_name, del_address, asd_contract_no1, asd_contract_no2,
				work_order_no, client_name, main_contractor,
				CAST(list(DISTINCT bbs_no) AS varchar(100)) AS bbs_no_list
			FROM (
				SELECT sh.id_hoja_ruta AS shipping_no,
					sh.fecha_hoja_ruta AS del_date,
					ph.id_obra AS jobsite_no,
					js.nombre AS jobsite_name, -- 1
					addr.direccion AS del_address, -- 2
					js.info_1 AS asd_contract_no1, -- 3
					CASE WHEN upper(addr.pais) containing ''''HONG KONG'''' THEN NULL ELSE addr.pais END AS asd_contract_no2, -- 4
					addr.codigo_postal AS work_order_no, -- 5
					clt.nombre AS client_name, -- 6
					js.arquitecto AS main_contractor, -- 7
					--list(DISTINCT ph.id_pedido_produccion) AS bbs_no
					ph.id_pedido_produccion AS bbs_no
				FROM hojas_ruta sh
				JOIN pedidos_produccion_lin pd
					ON pd.id_hoja_ruta = sh.id_hoja_ruta
				JOIN pedidos_produccion ph
					ON ph.id_pedido_produccion = pd.id_pedido_produccion
				JOIN obras js
					ON js.id_obra = ph.id_obra
						AND js.id_tipo_forjado = 5
				JOIN pedidos_cliente sc
					ON ph.id_pedido_cliente = sc.id_pedido_cliente
				JOIN direcciones_obras addr
					ON sc.id_direccion_obra = addr.id_direccion
				JOIN clientes clt
					ON clt.id_cliente = js.id_cliente
				WHERE sh.fecha_hoja_ruta between ''''{delivery_date}'''' AND current_date + 1
					AND ph.estado <> 15
				ORDER BY shipping_no, ph.id_pedido_produccion
			) aaa
			GROUP BY shipping_no, del_date, jobsite_no, jobsite_name, del_address, asd_contract_no1, asd_contract_no2,
				work_order_no, client_name, main_contractor
		'')
	'

	set @sql = replace( @sql, '{delivery_date}', convert(nvarchar(10), @currDate, 120) )

	truncate table cert_of_compliance

	insert into cert_of_compliance (shipping_no, del_date, jobsite_no, jobsite_name, del_address, 
		asd_contract_no1, asd_contract_no2, work_order_no, client_name, main_contractor, bbs_no_list)
	exec (@sql)

		
print('start: get list of BBS with missing TR (informational only; BBS are KEPT in DW)')
	-- Kept for ops visibility in sync log; no longer used to purge temp tables.
	SELECT DISTINCT tls.bbs_no
	INTO #bbs_with_missing_tr
	FROM #t_tr_line_size tls
	LEFT JOIN #t_tr_line_detail tld
		ON tls.bbs_no = tld.bbs_no
			AND tls.diameter = tld.diameter
	WHERE tld.product IS NULL

	DECLARE @missing_cnt INT = (SELECT COUNT(*) FROM #bbs_with_missing_tr)
	print('end: get list of BBS with missing TR, count=' + CAST(@missing_cnt AS VARCHAR(20)))
	-- incomplete BBS remain in #t_tr_* / #t_bbs_dd; PG bbs_tr_status marks selectable=false

	-- <<< tr_bbs_header  (KEEP incomplete BBS — do not delete)
	TRUNCATE TABLE tr_bbs_header

	INSERT INTO tr_bbs_header (bbs_no, order_desc, jobsite_no, jobsite_name, jobsite_type,
		main_contractor, delivery_date, bbs_ref_no, bbs_po_no)
	SELECT bbs_no, order_desc, jobsite_no, jobsite_name, jobsite_type,
		main_contractor, delivery_date, bbs_ref_no, bbs_po_no
	FROM #t_tr_bbs_header

	DROP TABLE #t_tr_bbs_header
	-- >>>

	-- <<< tr_line_size  (KEEP incomplete BBS)
	TRUNCATE TABLE tr_line_size

	INSERT INTO tr_line_size (jobsite_no, bbs_no, diameter, wt_ton)
	SELECT jobsite_no, bbs_no, diameter, wt_ton
	FROM #t_tr_line_size

	DROP TABLE #t_tr_line_size
	-- >>>

	-- <<< tr_line_detail
	TRUNCATE TABLE tr_line_detail

	INSERT INTO tr_line_detail ( jobsite_no, bbs_no, diameter,
		product, grade, pattern, mill_cert, test_cert1, test_cert2,
		supplier, stockist_cert, po_no, rm_dn_no )
	SELECT jobsite_no, bbs_no, diameter,
		product, grade, pattern, mill_cert, test_cert1, test_cert2,
		supplier, stockist_cert, po_no, rm_dn_no
	FROM #t_tr_line_detail

	DROP TABLE #t_tr_line_detail
	-- >>>

	-- <<< bbs_dd  (KEEP incomplete BBS)
	TRUNCATE TABLE bbs_dd

	INSERT INTO bbs_dd (bbs_no, order_desc, jobsite_no, jobsite_type,
		dd_no, dd_delivery_date)
	SELECT bbs_no, order_desc, jobsite_no, jobsite_type,
		dd_no, dd_delivery_date
	FROM #t_bbs_dd

	DROP TABLE #t_bbs_dd
	-- >>>

	IF OBJECT_ID('tempdb..#bbs_with_missing_tr') IS NOT NULL DROP TABLE #bbs_with_missing_tr
	

	
	/*
	select *
	from #t_tr_bbs_header

	select *
	from #t_tr_line_size

	select *
	from #t_tr_line_detail

	select *
	from #t_bbs_dd
	*/

	
	/*
	truncate table cert_of_compliance
	truncate table tr_bbs_header
	truncate table tr_line_size
	truncate table tr_line_detail
	truncate table bbs_dd

	
	insert into bbs_dd (bbs_no, order_desc, jobsite_no, jobsite_type,
		dd_no, dd_delivery_date)
	select bbs_no, order_desc, jobsite_no, jobsite_type,
		dd_no, dd_delivery_date
	from #t_bbs_dd

	insert into tr_bbs_header (bbs_no, order_desc, jobsite_no, jobsite_name, jobsite_type,
		main_contractor, delivery_date, bbs_ref_no, bbs_po_no)
	select bbs_no, order_desc, jobsite_no, jobsite_name, jobsite_type,
		main_contractor, delivery_date, bbs_ref_no, bbs_po_no
	from #t_tr_bbs_header

	insert into tr_line_size (jobsite_no, bbs_no, diameter, wt_ton)
	select jobsite_no, bbs_no, diameter, wt_ton
	from #t_tr_line_size

	insert into tr_line_detail ( jobsite_no, bbs_no, diameter,
		product, grade, pattern, mill_cert, test_cert1, test_cert2,
		supplier, stockist_cert, po_no, rm_dn_no )
	select jobsite_no, bbs_no, diameter,
		product, grade, pattern, mill_cert, test_cert1, test_cert2,
		supplier, stockist_cert, po_no, rm_dn_no
	from #t_tr_line_detail
	

	insert into cert_of_compliance (shipping_no, del_date, jobsite_no, jobsite_name, del_address, 
		asd_contract_no1, asd_contract_no2, work_order_no, client_name, main_contractor, bbs_no_list)
	select shipping_no, del_date, jobsite_no, jobsite_name, del_address, 
		asd_contract_no1, asd_contract_no2, work_order_no, client_name, main_contractor, bbs_no_list
	from #t_cert_of_compliance	
	*/

	/*
	select distinct tls.bbs_no
	from #t_tr_line_size tls
	left join #t_tr_line_detail tld
		on tls.bbs_no = tld.bbs_no
			and tls.diameter = tld.diameter
	where
		tld.product is null
	*/

END

/*
EXEC TVSC.dbo.sync_tr_data
*/