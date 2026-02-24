import { Column, CreateDateColumn, Entity, PrimaryGeneratedColumn, UpdateDateColumn } from 'typeorm';

@Entity('reports')
export class ReportDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: 'item_id' })
  item_id: number;

  @Column({ name: 'user_id' })
  user_id: number;

  @Column({ name: 'sticker_uri' })
  sticker_uri: string;

  @Column({ name: 'label_uri' })
  label_uri: string;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @Column()
  causer: string;

  @Column()
  gtin: string;
}
